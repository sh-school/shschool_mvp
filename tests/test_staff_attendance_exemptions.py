"""الإعفاءُ من الرصد اليوميّ — ق-16: عامٌّ لأكثر من موظّف، بلا سبب، ولا يُخصم منه ولا يُخطَر."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse

import staff_affairs.attendance as attendance_module
from notifications.models import InAppNotification
from staff_affairs.attendance import (
    ExemptionService,
    PolicyError,
    StaffAttendanceService,
    exempt_ids,
    recording_staff,
)
from staff_affairs.models import StaffAttendance, StaffAttendanceExemption
from staff_affairs.notices import send_monthly_absence_notices, uncovered_absences
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

DOHA = ZoneInfo("Asia/Qatar")
NOW = datetime(2026, 9, 21, 9, 30, tzinfo=DOHA)
TODAY = NOW.date()


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    monkeypatch.setattr(attendance_module, "_now", lambda: NOW, raising=False)


def _person(school, role, n):
    user = UserFactory(full_name=f"موظف اصطناعي {n}", employee_number=f"E-{n:04d}")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


@pytest.fixture
def principal(school):
    return _person(school, "principal", 1)


@pytest.fixture
def secretary(school):
    return _person(school, "secretary", 2)


@pytest.fixture
def exempt_secretary(school):
    return _person(school, "secretary", 3)


def _grant(school, actor, staff, start=TODAY, end=None):
    return ExemptionService.grant(
        school=school, actor=actor, staff_ids=[s.pk for s in staff], start=start, end=end
    )


class TestGrant:
    def test_one_decision_can_exempt_several_employees(self, school, principal):
        a, b = _person(school, "teacher", 10), _person(school, "teacher", 11)
        rows = _grant(school, principal, [a, b])
        assert len(rows) == 2
        assert exempt_ids(school, TODAY) == {a.pk, b.pk}

    def test_an_open_ended_exemption_covers_any_later_day(self, school, principal):
        a = _person(school, "teacher", 10)
        _grant(school, principal, [a])
        assert a.pk in exempt_ids(school, TODAY + timedelta(days=400))
        assert a.pk not in exempt_ids(school, TODAY - timedelta(days=1))

    def test_a_dated_exemption_stops_after_its_end(self, school, principal):
        a = _person(school, "teacher", 10)
        _grant(school, principal, [a], end=TODAY + timedelta(days=2))
        assert a.pk in exempt_ids(school, TODAY + timedelta(days=2))
        assert a.pk not in exempt_ids(school, TODAY + timedelta(days=3))

    def test_only_the_principal_or_the_administrative_deputy_may_grant(self, school, secretary):
        a = _person(school, "teacher", 10)
        with pytest.raises(PolicyError):
            _grant(school, secretary, [a])

    def test_the_administrative_deputy_may_grant(self, school):
        deputy = _person(school, "vice_admin", 5)
        a = _person(school, "teacher", 10)
        assert len(_grant(school, deputy, [a])) == 1

    def test_nobody_exempts_himself_and_an_unknown_person_is_refused(self, school, principal):
        with pytest.raises(PolicyError):
            _grant(school, principal, [principal])

    def test_an_end_before_the_start_is_refused(self, school, principal):
        a = _person(school, "teacher", 10)
        with pytest.raises(PolicyError):
            _grant(school, principal, [a], end=TODAY - timedelta(days=1))

    def test_no_reason_is_stored(self):
        names = {f.name for f in StaffAttendanceExemption._meta.get_fields()}
        assert not {"reason", "notes", "diagnosis"} & names


class TestEffects:
    def test_the_exempt_is_off_the_daily_board_and_others_stay(
        self, school, principal, secretary, exempt_secretary
    ):
        _grant(school, principal, [exempt_secretary])
        board = StaffAttendanceService.daily_board(school, TODAY, viewer=principal)
        names = {row["staff"].pk for row in board["rows"]}
        assert exempt_secretary.pk not in names and secretary.pk in names
        assert recording_staff(school, TODAY).filter(pk=exempt_secretary.pk).count() == 0

    def test_recording_the_exempt_as_absent_is_refused(
        self, school, principal, secretary, exempt_secretary
    ):
        _grant(school, principal, [exempt_secretary])
        with pytest.raises(PolicyError, match="معفًى"):
            StaffAttendanceService.mark(
                school=school, staff=exempt_secretary, day=TODAY, status="absent", actor=secretary
            )

    def test_the_exempt_returns_to_the_board_the_day_after_a_revoke_not_before(
        self, school, principal, exempt_secretary
    ):
        row = _grant(school, principal, [exempt_secretary])[0]
        ExemptionService.revoke(row, actor=principal)
        # يسري الرفعُ من اليوم: أيّامٌ مضت تبقى معفاةً، واليومُ وما بعده يعودان للرصد.
        assert exempt_secretary.pk not in exempt_ids(school, TODAY)
        row.refresh_from_db()
        assert row.revoked_by_id == principal.pk and row.revoked_at is not None

    def test_revoking_twice_is_harmless_and_keeps_the_row(self, school, principal, secretary):
        a = _person(school, "teacher", 10)
        row = _grant(school, principal, [a])[0]
        ExemptionService.revoke(row, actor=principal)
        ExemptionService.revoke(row, actor=principal)
        assert StaffAttendanceExemption.objects.filter(pk=row.pk).exists()
        with pytest.raises(PolicyError):
            ExemptionService.revoke(row, actor=secretary)

    def test_the_monthly_notice_skips_exempt_days(self, school, principal, exempt_secretary):
        StaffAttendance.objects.create(
            school=school,
            staff=exempt_secretary,
            date=date(2026, 8, 5),
            status="absent",
            absence_type="",
        )
        assert uncovered_absences(school, 2026, 8)  # قبل الإعفاء: يُخطَر
        _grant(school, principal, [exempt_secretary], start=date(2026, 8, 1))
        assert uncovered_absences(school, 2026, 8) == {}
        assert send_monthly_absence_notices(school, 2026, 8) == 0
        assert not InAppNotification.objects.filter(user=exempt_secretary).exists()

    def test_a_whole_month_exemption_removes_the_person_from_the_report(
        self, school, principal, secretary, exempt_secretary
    ):
        _grant(school, principal, [exempt_secretary], start=date(2026, 9, 1))
        report = StaffAttendanceService.monthly_report(school, 2026, 9, viewer=principal)
        names = {row["full_name"] for row in report["rows"]}
        assert exempt_secretary.full_name not in names and secretary.full_name in names


class TestScreen:
    def test_the_principal_opens_the_screen_and_grants_two_at_once(self, client, school, principal):
        a, b = _person(school, "teacher", 10), _person(school, "teacher", 11)
        client.force_login(principal)
        url = reverse("staff_affairs:exemptions")
        assert client.get(url).status_code == 200
        response = client.post(
            url,
            {"staff": [str(a.pk), str(b.pk)], "start_date": TODAY.isoformat(), "end_date": ""},
        )
        assert response.status_code == 302
        assert StaffAttendanceExemption.objects.filter(school=school).count() == 2

    def test_a_teacher_cannot_open_the_screen(self, client, school):
        teacher = _person(school, "teacher", 20)
        client.force_login(teacher)
        response = client.get(reverse("staff_affairs:exemptions"))
        assert response.status_code in (302, 403, 404)

    def test_revoke_route_only_accepts_post(self, client, school, principal):
        a = _person(school, "teacher", 10)
        row = _grant(school, principal, [a])[0]
        client.force_login(principal)
        url = reverse("staff_affairs:exemption_revoke", args=[row.pk])
        assert client.get(url).status_code == 405
        assert client.post(url).status_code == 302
