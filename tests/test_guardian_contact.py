"""إخطارُ وليّ الأمر بضغطةٍ من المشرف — والإخطارُ سجلٌّ لا يحرّك مهلةَ العذر (قرارُ 2026-09-14).

- «اتّصلتُ بوليّ الأمر» يُسجَّل بنتيجته (ردّ / لم يردّ / سيُحضر عذراً) عن يومِ غيابٍ بعينه.
- الكشفُ يُعلّم من غاب أمس ولم يُخطَر أهلُه، ويُسقط العلامةَ بعد الإخطار — ولو «لم يردّ».
- والإخطارُ لا يحرّك مهلةَ العذر: تُعدّ من عودة الطالب (قرارُ 2026-09-14).
"""

import datetime as dt

import pytest
from django.urls import reverse

from operations.excuses import deadline_of, grant_excuse
from operations.guardian_contact import ContactError, awaiting_contact, log_contact
from operations.models import GuardianContact
from tests.test_period_register import (  # noqa: F401 — التجهيزاتُ نفسُها
    SUNDAY,
    _confirm,
    _periods,
    at,
    kids,
    klass,
    subjects,
    supervisor,
    teacher,
    year,
)

pytestmark = pytest.mark.django_db

MONDAY = SUNDAY + dt.timedelta(days=1)


def _absent_sunday(school, klass, kid, teacher, supervisor):
    for session in _periods(school, klass, teacher, 7):
        _confirm(klass, session, {kid: "absent"}, supervisor)


class TestLogging:
    def test_a_contact_is_recorded_with_its_outcome_and_moment(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _absent_sunday(school, klass, kids[0], teacher, supervisor)

        contact = log_contact(
            student=kids[0],
            school=school,
            absence_date=SUNDAY,
            outcome="no_answer",
            by=supervisor,
            now=at(13, 5),
        )

        assert (contact.outcome, contact.channel, contact.contacted_by) == (
            "no_answer",
            "phone",
            supervisor,
        )
        assert contact.contacted_at == at(13, 5)

    def test_an_unknown_outcome_is_refused(self, school, seeded_calendar, klass, kids, supervisor):
        with pytest.raises(ContactError):
            log_contact(
                student=kids[0], school=school, absence_date=SUNDAY, outcome="maybe", by=supervisor
            )


class TestTheRegisterFlagsWhoWasNotNotified:
    def test_absent_yesterday_without_a_contact_is_flagged_then_cleared(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _absent_sunday(school, klass, kids[0], teacher, supervisor)
        _periods(school, klass, teacher, 7, day=MONDAY)

        assert awaiting_contact(klass, MONDAY) == {kids[0].id: SUNDAY}

        log_contact(
            student=kids[0], school=school, absence_date=SUNDAY, outcome="no_answer", by=supervisor
        )

        assert awaiting_contact(klass, MONDAY) == {}, "«لم يردّ» إخطارٌ أيضاً"

    def test_an_excused_absence_needs_no_call(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _absent_sunday(school, klass, kids[0], teacher, supervisor)
        grant_excuse(
            student=kids[0],
            school=school,
            date_from=SUNDAY,
            date_to=SUNDAY,
            kind="bereavement",
            notes="الأب",
            by=supervisor,
            today=MONDAY,
        )
        _periods(school, klass, teacher, 7, day=MONDAY)

        assert awaiting_contact(klass, MONDAY) == {}

    def test_the_sheet_shows_the_flag_linking_to_the_students_page(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _absent_sunday(school, klass, kids[0], teacher, supervisor)
        _periods(school, klass, teacher, 7, day=MONDAY)

        body = (
            client_as(supervisor)
            .get(reverse("wings:record_section", args=[klass.id]) + f"?date={MONDAY.isoformat()}")
            .content.decode()
        )

        assert body.count("لم يُخطَر وليُّ الأمر") == 1
        assert reverse("wings:student_events", args=[klass.id, kids[0].id]) in body


class TestTheCallDoesNotMoveTheDeadline:
    def test_the_deadline_runs_from_the_return_whatever_the_call(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        """غاب الأحد وعاد الاثنين، وأُخطر أهلُه الأربعاء: المهلةُ حتى الأربعاء نفسِه."""
        _absent_sunday(school, klass, kids[0], teacher, supervisor)
        for session in _periods(school, klass, teacher, 4, day=MONDAY):
            _confirm(klass, session, {}, supervisor, day=MONDAY)
        wednesday = SUNDAY + dt.timedelta(days=3)
        before = deadline_of(school, kids[0], SUNDAY)

        log_contact(
            student=kids[0],
            school=school,
            absence_date=SUNDAY,
            outcome="will_excuse",
            by=supervisor,
            now=at(9, 0, day=wednesday),
        )

        assert before == wednesday
        assert deadline_of(school, kids[0], SUNDAY) == wednesday


class TestTheScreen:
    def test_the_supervisor_logs_a_call_from_the_students_page(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _absent_sunday(school, klass, kids[0], teacher, supervisor)
        client = client_as(supervisor)
        page_url = reverse("wings:student_events", args=[klass.id, kids[0].id])

        assert "اتّصلتُ بوليّ الأمر" in client.get(page_url).content.decode()

        response = client.post(
            reverse("wings:guardian_contact_log", args=[klass.id, kids[0].id]),
            {"absence_date": SUNDAY.isoformat(), "outcome": "answered", "note": "سيُحضر تقريراً"},
        )

        assert response.status_code == 302 and response.url == page_url
        contact = GuardianContact.objects.get(student=kids[0])
        assert (contact.outcome, contact.note, contact.contacted_by) == (
            "answered",
            "سيُحضر تقريراً",
            supervisor,
        )
        assert "سيُحضر تقريراً" in client.get(page_url).content.decode()

    def test_a_supervisor_of_another_wing_is_turned_away(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        from tests.conftest import MembershipFactory, RoleFactory, UserFactory

        stranger = UserFactory(full_name="مشرفٌ آخر", national_id="29300000095")
        MembershipFactory(
            user=stranger, school=school, role=RoleFactory(school=school, name="admin_supervisor")
        )

        response = client_as(stranger).post(
            reverse("wings:guardian_contact_log", args=[klass.id, kids[0].id]),
            {"absence_date": SUNDAY.isoformat(), "outcome": "answered"},
        )

        assert response.status_code == 404
        assert not GuardianContact.objects.exists()
