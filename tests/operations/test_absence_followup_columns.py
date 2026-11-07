"""تعديلُ متابعة الغياب (W-20261014-018) — عمودا «المتابعة» لثلاثة أدوارٍ فقط، والخيارات، والاحتسابُ بالحصّتين.

الحجبُ في الخدمة فيُفحص على الشاشة الفعليّة وعلى PDF الناتج لا على القالب وحده.
"""

import datetime as dt
import io

import pdfplumber
import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from operations.absence_followup_print import build_followup_pdf
from operations.models import AbsenceActionLog, AbsenceContactLog
from operations.services import absence_followup as svc
from tests.operations.test_absence_followup import (  # noqa: F401
    DAY,
    _calendar_first,
    _get,
    _post_action,
    _post_contact,
    absent_both,
    second_wing,
    staff,
)
from tests.test_period_register import (  # noqa: F401
    SUNDAY,
    _confirm,
    _periods,
    kids,
    klass,
    other_teacher,
    subjects,
    supervisor,
    teacher,
    year,
)

pytestmark = pytest.mark.django_db

SIX = ["غياب بدون عذر", "غياب بعذر طبي", "مفصول داخليًّا", "مفصول خارجيًّا", "ولي الأمر لم يرد", "أخرى"]
STATUS_LABELS = ["لم تتمّ المتابعة", "تمّ جزئياً"]


def _pdf_marks(user, school):
    """عدّ كلمة «متابعة» في PDF الناتج (معكوسةً أو لا، بلا تشكيل) — عمودا المتابعة يزيدانه بمقدار اثنين على العنوان."""
    import re

    try:
        result = build_followup_pdf(school, user, {"date": DAY, "page": "actions"})
    except PermissionDenied:
        return None
    pages = pdfplumber.open(io.BytesIO(result.content)).pages
    raw = chr(10).join(p.extract_text() or "" for p in pages)
    flat = re.sub(r"[ً-ْ\s]", "", raw)
    return flat.count("متابعة") + flat.count("متابعة"[::-1])


def _seed_status(client_as, principal, kid):
    _post_contact(client_as, principal, kid, status="partial")
    _post_action(client_as, principal, kid, status="not_followed")


class TestColumnsByRole:
    @pytest.mark.parametrize("role", ["principal", "vice_admin", "coordinator"])
    def test_the_three_roles_see_the_columns_on_screen_and_in_the_pdf(
        self, client_as, staff, supervisor, absent_both, school, role
    ):
        _seed_status(client_as, staff["principal"], absent_both[0])
        body = _get(client_as, staff[role], "absence_actions").content.decode()
        assert ">متابعةُ الإجراء</th>" in body and "وقتُ المتابعة ومن سجّلها" in body
        assert ">متابعةُ التواصل</th>" not in _get(client_as, staff[role]).content.decode()
        assert _pdf_marks(supervisor, school) is None, "الطباعةُ لثلاثةٍ فقط"
        assert _pdf_marks(staff[role], school) >= 3

    def test_the_wing_supervisor_and_academic_deputy_get_none_of_it(
        self, client_as, staff, supervisor, absent_both, school
    ):
        _seed_status(client_as, staff["principal"], absent_both[0])
        for user in (supervisor, staff["vice_academic"]):
            body = _get(client_as, user, "absence_actions").content.decode()
            assert ">متابعةُ الإجراء</th>" not in body and "وقتُ المتابعة" not in body
            rows = svc.followup_rows(user, SUNDAY)
            assert all(r["contact_status"] == "" and r["action_status"] == "" for r in rows)
            assert _pdf_marks(user, school) is None

    def test_a_non_holder_cannot_write_a_follow_up_only_status(
        self, staff, supervisor, absent_both
    ):
        kid = absent_both[0]
        with pytest.raises(PermissionDenied):
            svc.record_action(supervisor, kid.id, SUNDAY, "other", "not_followed")


class TestOptions:
    def test_the_six_outcomes_are_verbatim_and_other_needs_text(
        self, client_as, staff, absent_both
    ):
        labels = [str(lbl) for _, lbl in AbsenceContactLog.OUTCOMES[:6]]
        assert labels == SIX
        body = _get(client_as, staff["principal"]).content.decode()
        for label in SIX:
            assert label in body
        kid = absent_both[0]
        _post_contact(client_as, staff["principal"], kid, outcome="other")
        assert not AbsenceContactLog.objects.exists()
        _post_contact(client_as, staff["principal"], kid, outcome="other", feedback="سببٌ آخر")
        assert AbsenceContactLog.objects.get().outcome == "other"

    def test_a_legacy_outcome_is_not_offered_for_a_new_record(self, client_as, staff, absent_both):
        _post_contact(client_as, staff["principal"], absent_both[0], outcome="answered")
        assert not AbsenceContactLog.objects.exists()

    def test_the_two_referrals_and_the_pledge_label(self, client_as, staff, absent_both):
        body = _get(client_as, staff["principal"], "absence_actions").content.decode()
        assert "تحويل لمنسق شؤون الطلاب" in body and "تحويل للأخصائي الاجتماعي" in body
        assert "إشعار كتابي" not in body and "تعهد خطي" in body

    def test_an_old_written_notice_row_reads_as_a_pledge_unchanged(
        self, client_as, staff, absent_both
    ):
        _post_action(client_as, staff["principal"], absent_both[0], action_kind="written_notice")
        row = AbsenceActionLog.objects.get()
        assert row.action_kind == "written_notice"
        assert row.get_action_kind_display() == "تعهد خطي"
        assert "تعهد خطي" in _get(client_as, staff["principal"], "absence_actions").content.decode()


class TestCounting:
    def test_one_period_absence_is_not_counted_and_two_periods_are(
        self, school, klass, kids, teacher, supervisor, staff
    ):
        sessions = _periods(school, klass, teacher, 7, day=SUNDAY)
        _confirm(klass, sessions[0], {kids[0]: "absent"}, supervisor)
        for s in sessions[1:]:
            _confirm(klass, s, {}, supervisor)
        assert svc.followup_rows(staff["principal"], SUNDAY) == []
        _confirm(klass, sessions[1], {kids[0]: "absent"}, supervisor)
        rows = svc.followup_rows(staff["principal"], SUNDAY)
        assert [r["student"] for r in rows] == [kids[0]]


class TestPrintFollowsScreen:
    def test_the_pdf_rows_equal_the_filtered_sorted_screen(
        self, client_as, staff, second_wing, absent_both, school
    ):
        principal = staff["principal"]
        _post_contact(client_as, principal, absent_both[0])
        for params in ({"followup": "no_contact"}, {"grade": "G8"}, {"sort": "name"}):
            rows = svc.apply_view(svc.followup_rows(principal, SUNDAY), **params)
            result = build_followup_pdf(school, principal, {"date": DAY, **params})
            assert result.rows == len(rows)
        forged = build_followup_pdf(school, principal, {"date": DAY, "sort": "'; drop"})
        assert forged.rows == len(svc.followup_rows(principal, SUNDAY))


class TestAbsentDaysColumn:
    """عمودُ «أيام الغياب» (W-20261107-018): أيامُ العام التي غاب فيها الحصّتين معاً، باستعلامٍ مجمَّعٍ."""

    @staticmethod
    def _seed(school, klass, kids, teacher, supervisor):
        """يومان بغياب الحصّتين (الثاني هو يومُ التقرير) ويومٌ بغياب الأولى وحدَها قبلهما."""
        both = [SUNDAY + dt.timedelta(days=7), SUNDAY + dt.timedelta(days=14)]
        for day, periods in ((SUNDAY, 1), (both[0], 2), (both[1], 2)):
            sessions = _periods(school, klass, teacher, 7, day=day)
            for i, session in enumerate(sessions):
                marks = {kids[0]: "absent"} if i < periods else {}
                if day == both[1] and i < 2:
                    marks[kids[1]] = "absent"
                _confirm(klass, session, marks, supervisor, day=day)
        return both[1]

    def test_two_full_days_and_a_first_period_only_day_count_two(
        self, school, klass, kids, teacher, supervisor, staff
    ):
        report_day = self._seed(school, klass, kids, teacher, supervisor)
        found = svc.followup_rows(staff["principal"], report_day)
        rows = {r["student"]: r["absent_days"] for r in found}
        assert rows[kids[0]] == 2
        assert rows[kids[1]] == 1

    def test_queries_do_not_grow_with_the_rows(
        self, school, klass, kids, teacher, supervisor, staff
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        report_day = self._seed(school, klass, kids, teacher, supervisor)
        with CaptureQueriesContext(connection) as one:
            svc.absence_days_for(school, [kids[0].id], report_day)
        with CaptureQueriesContext(connection) as many:
            svc.absence_days_for(school, [k.id for k in kids], report_day)
        assert len(many) == len(one)

    def test_column_shows_on_screen_pdf_and_excel_and_sorts(
        self, client_as, school, klass, kids, teacher, supervisor, staff
    ):
        from operations.absence_followup_print import _xlsx_table

        report_day = self._seed(school, klass, kids, teacher, supervisor)
        principal = staff["principal"]
        iso = f"{report_day:%Y-%m-%d}"
        response = client_as(principal).get(reverse("absence_actions"), {"date": iso})
        assert "أيامُ الغياب</th>" in response.content.decode()
        rows = svc.apply_view(svc.followup_rows(principal, report_day), sort="days")
        assert [r["absent_days"] for r in rows] == [2, 1]
        titled = [dict(r, wing_title="") for r in rows]
        _, columns, data = _xlsx_table("actions", titled, False)
        index = [name for name, _ in columns].index("أيام الغياب")
        assert [line[index] for line in data] == [2, 1]
        result = build_followup_pdf(school, principal, {"date": iso, "page": "actions"})
        assert result.rows == 2
