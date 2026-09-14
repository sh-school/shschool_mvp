"""تحويلُ الغياب «بلا عذر» إلى «بعذرٍ مقبول» عند المشرف (قرارُ 2026-09-13).

- القائمةُ مغلقةٌ بخمسة (الدليل 2026 م 3.4.1.4) — «أخرى» لا تُقبل.
- المستندُ شرطٌ حيث اشترطه النصّ (طبّيّ، كتابٌ رسميّ…)، والوفاةُ ببيان القرابة.
- المهلةُ يومان من آخر يومِ غياب (م 3.4.1.5): المشرفُ في المهلة، والنائبُ بعدها بسبب.
- العذرُ يغطّي كلَّ حصص المدّة ويُسقط اليومَ من عدّ الحرمان؛ وإلغاؤه يُعيدها — وكلاهما في سجلّ المراجعة.
"""

import datetime as dt

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from core.models import AuditLog
from operations.absence_standing import standing_for
from operations.excuses import ExcuseError, grant_excuse, revoke_excuse
from operations.models import AbsenceExcuse, StudentAttendance
from tests.conftest import MembershipFactory, RoleFactory, UserFactory
from tests.test_period_register import (  # noqa: F401 — التجهيزاتُ نفسُها
    SUNDAY,
    _confirm,
    _periods,
    kids,
    klass,
    subjects,
    supervisor,
    teacher,
    year,
)

pytestmark = pytest.mark.django_db

MONDAY = SUNDAY + dt.timedelta(days=1)


@pytest.fixture
def vice_admin(school):
    user = UserFactory(full_name="النائب الإداريّ", national_id="29300000093")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="vice_admin"))
    return user


def _absent_day(school, klass, kid, teacher, supervisor, day=SUNDAY, count=7):
    """يومٌ كاملٌ غائبٌ فيه الطالب — مثبَّتٌ من المشرف."""
    for session in _periods(school, klass, teacher, count, day=day):
        _confirm(klass, session, {kid: "absent"}, supervisor, day=day)


def _report():
    return SimpleUploadedFile("report.pdf", b"%PDF-1.4 fake", content_type="application/pdf")


class TestGranting:
    def test_the_excuse_covers_every_absent_period_and_drops_the_day_from_the_count(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _absent_day(school, klass, kids[0], teacher, supervisor)
        assert standing_for(kids[0], school, grade="G7", on=SUNDAY).unexcused_days == 1

        excuse = grant_excuse(
            student=kids[0],
            school=school,
            date_from=SUNDAY,
            date_to=SUNDAY,
            kind="medical",
            document=_report(),
            by=supervisor,
            today=MONDAY,
        )

        rows = StudentAttendance.objects.filter(student=kids[0], status="absent")
        assert rows.count() == 7 and all(r.excuse_type == "medical" for r in rows)
        assert all(r.excuse_id == excuse.pk for r in rows)
        standing = standing_for(kids[0], school, grade="G7", on=SUNDAY)
        assert (standing.unexcused_days, standing.excused_days) == (0, 1)
        assert not excuse.after_deadline

    def test_only_the_closed_list_is_accepted(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _absent_day(school, klass, kids[0], teacher, supervisor)

        with pytest.raises(ExcuseError, match="القائمة المغلقة"):
            grant_excuse(
                student=kids[0],
                school=school,
                date_from=SUNDAY,
                date_to=SUNDAY,
                kind="other",
                by=supervisor,
                today=MONDAY,
            )

    def test_a_medical_excuse_needs_its_report_and_bereavement_needs_the_relation(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _absent_day(school, klass, kids[0], teacher, supervisor)
        common = {
            "student": kids[0],
            "school": school,
            "date_from": SUNDAY,
            "date_to": SUNDAY,
            "by": supervisor,
        }

        with pytest.raises(ExcuseError, match="التقريرُ الطبّيّ"):
            grant_excuse(kind="medical", today=MONDAY, **common)
        with pytest.raises(ExcuseError, match="صلةَ القرابة"):
            grant_excuse(kind="bereavement", today=MONDAY, **common)

        excuse = grant_excuse(kind="bereavement", notes="الأب", today=MONDAY, **common)
        assert excuse.pk and not excuse.document

    def test_nothing_to_excuse_is_refused(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _periods(school, klass, teacher, 2)

        with pytest.raises(ExcuseError, match="لا غيابَ"):
            grant_excuse(
                student=kids[0],
                school=school,
                date_from=SUNDAY,
                date_to=SUNDAY,
                kind="bereavement",
                notes="الأمّ",
                by=supervisor,
                today=MONDAY,
            )

    def test_an_already_excused_period_is_left_alone(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _absent_day(school, klass, kids[0], teacher, supervisor)
        first = grant_excuse(
            student=kids[0],
            school=school,
            date_from=SUNDAY,
            date_to=SUNDAY,
            kind="bereavement",
            notes="الجدّ",
            by=supervisor,
            today=MONDAY,
        )

        with pytest.raises(ExcuseError, match="لا غيابَ"):
            grant_excuse(
                student=kids[0],
                school=school,
                date_from=SUNDAY,
                date_to=SUNDAY,
                kind="medical",
                document=_report(),
                by=supervisor,
                today=MONDAY,
            )
        assert AbsenceExcuse.objects.get() == first


class TestTheDeadline:
    def test_the_two_days_are_school_days_not_calendar_days(self, school, seeded_calendar):
        """قرارُ 2026-09-14: يومان دراسيّان — الخميسُ تليه الجمعةُ والسبتُ فلا يُعدّان."""
        from operations.excuses import deadline_of, is_after_deadline

        thursday = dt.date(2026, 9, 17)
        assert deadline_of(school, thursday) == dt.date(2026, 9, 21), "الأحدُ الأوّل والاثنينُ الثاني"
        assert not is_after_deadline(school, thursday, dt.date(2026, 9, 21))
        assert is_after_deadline(school, thursday, dt.date(2026, 9, 22))

    def test_a_ministry_break_does_not_count_against_the_guardian(self, school, seeded_calendar):
        """إجازةُ منتصف الفصل (25–29 أكتوبر 2026) تقفز فوقها المهلة."""
        from operations.excuses import deadline_of

        assert deadline_of(school, dt.date(2026, 10, 22)) == dt.date(2026, 11, 2)

    def test_after_two_days_the_supervisor_is_refused(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _absent_day(school, klass, kids[0], teacher, supervisor)

        with pytest.raises(ExcuseError, match="انقضت مهلةُ اليومين"):
            grant_excuse(
                student=kids[0],
                school=school,
                date_from=SUNDAY,
                date_to=SUNDAY,
                kind="medical",
                document=_report(),
                by=supervisor,
                today=SUNDAY + dt.timedelta(days=3),
            )

    def test_the_vice_admin_accepts_after_the_deadline_with_a_written_reason(
        self, school, seeded_calendar, klass, kids, teacher, supervisor, vice_admin
    ):
        _absent_day(school, klass, kids[0], teacher, supervisor)
        common = {
            "student": kids[0],
            "school": school,
            "date_from": SUNDAY,
            "date_to": SUNDAY,
            "kind": "medical",
            "document": _report(),
            "by": vice_admin,
            "today": SUNDAY + dt.timedelta(days=3),
            "may_override": True,
        }

        with pytest.raises(ExcuseError, match="سببَ القبول"):
            grant_excuse(**common)

        excuse = grant_excuse(override_reason="التقريرُ وصل متأخّراً من المستشفى", **common)
        assert excuse.after_deadline and excuse.override_reason
        assert standing_for(kids[0], school, grade="G7", on=SUNDAY).unexcused_days == 0

    def test_the_second_day_is_still_inside_the_window(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _absent_day(school, klass, kids[0], teacher, supervisor)

        excuse = grant_excuse(
            student=kids[0],
            school=school,
            date_from=SUNDAY,
            date_to=SUNDAY,
            kind="bereavement",
            notes="الأخ",
            by=supervisor,
            today=SUNDAY + dt.timedelta(days=2),
        )

        assert not excuse.after_deadline


class TestRevoking:
    def test_revoking_restores_the_rows_and_both_moves_are_audited(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _absent_day(school, klass, kids[0], teacher, supervisor)
        excuse = grant_excuse(
            student=kids[0],
            school=school,
            date_from=SUNDAY,
            date_to=SUNDAY,
            kind="bereavement",
            notes="الأب",
            by=supervisor,
            today=MONDAY,
        )

        with pytest.raises(ExcuseError, match="سببَ الإلغاء"):
            revoke_excuse(excuse, by=supervisor, reason="  ")
        restored = revoke_excuse(excuse, by=supervisor, reason="القرابةُ من الدرجة الثانية")

        assert restored == 7
        assert not AbsenceExcuse.objects.exists()
        assert not StudentAttendance.objects.filter(excuse_type="bereavement").exists()
        assert standing_for(kids[0], school, grade="G7", on=SUNDAY).unexcused_days == 1
        logs = AuditLog.objects.filter(object_repr__startswith="عذرُ غياب").order_by("timestamp")
        assert [log.action for log in logs] == ["create", "delete"]
        assert logs[1].changes["reason"] == "القرابةُ من الدرجة الثانية"


class TestTheScreen:
    def test_the_supervisor_grants_from_the_students_page(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _absent_day(school, klass, kids[0], teacher, supervisor)
        client = client_as(supervisor)
        page_url = reverse("wings:student_events", args=[klass.id, kids[0].id])

        page = client.get(page_url).content.decode()
        assert "اقبل العذر" in page
        assert "سببُ القبول بعد المهلة" not in page, "المشرفُ لا يرى حقلَ ما بعد المهلة"
        assert 'value="other"' not in page, "«أخرى» ليست في القائمة"

        response = client.post(
            reverse("wings:excuse_grant", args=[klass.id, kids[0].id]),
            {
                "date_from": SUNDAY.isoformat(),
                "date_to": SUNDAY.isoformat(),
                "kind": "medical",
                "document": _report(),
            },
        )

        assert response.status_code == 302 and response.url == page_url
        excuse = AbsenceExcuse.objects.get(student=kids[0])
        assert excuse.granted_by == supervisor and excuse.document
        page = client.get(page_url).content.decode()
        assert "بعذر: مرضٌ بتقريرٍ طبّيّ" in page

    def test_the_vice_admin_sees_the_override_field(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor, vice_admin
    ):
        page = (
            client_as(vice_admin)
            .get(reverse("wings:student_events", args=[klass.id, kids[0].id]))
            .content.decode()
        )

        assert "سببُ القبول بعد المهلة" in page

    def test_a_supervisor_of_another_wing_is_turned_away(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        stranger = UserFactory(full_name="مشرفٌ آخر", national_id="29300000094")
        MembershipFactory(
            user=stranger, school=school, role=RoleFactory(school=school, name="admin_supervisor")
        )

        response = client_as(stranger).post(
            reverse("wings:excuse_grant", args=[klass.id, kids[0].id]),
            {"date_from": SUNDAY.isoformat(), "kind": "bereavement", "notes": "الأب"},
        )

        assert response.status_code == 404
        assert not AbsenceExcuse.objects.exists()

    def test_the_revoke_form_works_from_the_page(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _absent_day(school, klass, kids[0], teacher, supervisor)
        excuse = grant_excuse(
            student=kids[0],
            school=school,
            date_from=SUNDAY,
            date_to=SUNDAY,
            kind="bereavement",
            notes="الأب",
            by=supervisor,
            today=MONDAY,
        )

        client_as(supervisor).post(
            reverse("wings:excuse_revoke", args=[excuse.pk]), {"reason": "خطأٌ في الطالب"}
        )

        assert not AbsenceExcuse.objects.exists()
        assert StudentAttendance.objects.filter(student=kids[0], excuse_type="").count() == 7
