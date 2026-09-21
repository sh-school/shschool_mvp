"""إخطاراتُ الحضور للموظّفين — سياسة 5.1: تقريرُ أيام الغياب أوّلَ كلّ شهر، وإخطارُ اعتماد الإذن."""

from __future__ import annotations

from datetime import date, time
from unittest import mock

import pytest

from notifications.models import InAppNotification
from staff_affairs.models import PermitRequest, StaffAttendance
from staff_affairs.notices import send_monthly_absence_notices, uncovered_absences
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db


def _staff(school, n, email=""):
    user = UserFactory(full_name=f"موظف اصطناعي {n}", employee_number=f"N-{n:04d}", email=email)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


def _absent(school, staff, day, absence_type=""):
    return StaffAttendance.objects.create(
        school=school, staff=staff, date=day, status="absent", absence_type=absence_type
    )


AUG = date(2026, 8, 1)


class TestMonthlyAbsenceNotice:
    def test_only_uncovered_absences_are_reported_per_staff(self, school):
        a, b, c = _staff(school, 1), _staff(school, 2), _staff(school, 3)
        _absent(school, a, date(2026, 8, 3))
        _absent(school, a, date(2026, 8, 4))
        _absent(school, b, date(2026, 8, 5), absence_type="sick")  # غُطّي بنوعٍ من سجلّ الغياب
        StaffAttendance.objects.create(
            school=school, staff=c, date=date(2026, 8, 6), status="present", check_in=time(7, 0)
        )
        _absent(school, c, date(2026, 7, 30))  # شهرٌ آخر

        found = uncovered_absences(school, 2026, 8)

        assert {s.pk: days for s, days in found.items()} == {
            a.pk: [date(2026, 8, 3), date(2026, 8, 4)]
        }

    def test_the_notice_lists_the_days_and_the_deadline_and_never_repeats(self, school):
        a = _staff(school, 1)
        _absent(school, a, date(2026, 8, 3))
        _absent(school, a, date(2026, 8, 4))

        assert send_monthly_absence_notices(school, 2026, 8) == 1
        assert send_monthly_absence_notices(school, 2026, 8) == 0  # لا تكرار

        note = InAppNotification.objects.get(user=a)
        assert "2 يومُ غياب" in note.body and "03/08، 04/08" in note.body
        assert "قبل يوم 15" in note.body and "الخصمُ" in note.body
        assert note.title == "تقرير أيام الغياب عن شهر 08/2026"

    def test_the_notice_never_carries_the_absence_reason(self, school):
        a = _staff(school, 1)
        _absent(school, a, date(2026, 8, 3))
        send_monthly_absence_notices(school, 2026, 8)
        body = InAppNotification.objects.get(user=a).body
        assert "مرض" not in body and "عذر" not in body.split("(")[0]

    def test_email_goes_through_the_platform_queue_only_when_the_staff_has_one(
        self, school, django_capture_on_commit_callbacks
    ):
        with_mail = _staff(school, 1, email="synthetic1@example.invalid")
        without = _staff(school, 2)
        _absent(school, with_mail, date(2026, 8, 3))
        _absent(school, without, date(2026, 8, 3))

        with (
            mock.patch("notifications.tasks.send_email_task.delay") as delay,
            django_capture_on_commit_callbacks(execute=True),
        ):
            assert send_monthly_absence_notices(school, 2026, 8) == 2

        assert delay.call_count == 1
        kwargs = delay.call_args.kwargs
        assert kwargs["recipient_email"] == "synthetic1@example.invalid"
        assert kwargs["school_id"] == str(school.pk)
        assert InAppNotification.objects.filter(user=without).exists()  # المنصّةُ تصل بلا بريد

    def test_the_monthly_task_targets_the_previous_month_and_is_scheduled(self, school):
        from shschool.celery import app
        from staff_affairs.tasks import send_monthly_absence_notices_task

        a = _staff(school, 1)
        _absent(school, a, date(2026, 8, 3))
        with mock.patch("staff_affairs.tasks.timezone.localdate", return_value=date(2026, 9, 1)):
            result = send_monthly_absence_notices_task()

        assert result == {"notified": 1}
        entries = [
            e
            for e in app.conf.beat_schedule.values()
            if e["task"] == "staff_affairs.send_monthly_absence_notices"
        ]
        assert len(entries) == 1
        assert entries[0]["schedule"].day_of_month == {1}


class TestPermitApprovalEmail:
    def test_the_approval_notice_is_emailed_without_the_reason(
        self, school, django_capture_on_commit_callbacks
    ):
        from staff_affairs.attendance import PermitService

        staff = _staff(school, 1, email="synthetic1@example.invalid")
        permit = PermitRequest.objects.create(
            school=school,
            staff=staff,
            permit_type="during_day",
            date=date(2026, 2, 10),
            start_time=time(10, 0),
            end_time=time(11, 0),
            duration_minutes=60,
            reason="سببٌ قد يحمل بيانةً صحّيّة",
            status="approved",
            stage="closed",
            deputy_role="vice_academic",
        )
        with (
            mock.patch("notifications.tasks.send_email_task.delay") as delay,
            django_capture_on_commit_callbacks(execute=True),
        ):
            PermitService._notify(permit)

        assert delay.call_count == 1
        body = delay.call_args.kwargs["body_text"]
        assert "10:00" in body and "11:00" in body
        assert "بيانةً صحّيّة" not in body
        assert InAppNotification.objects.filter(user=staff).exists()
