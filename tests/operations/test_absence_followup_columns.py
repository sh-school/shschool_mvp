"""تعديلُ متابعة الغياب (W-20261014-018) — عمودا «المتابعة» لثلاثة أدوارٍ فقط، والخيارات، والاحتسابُ بالحصّتين.

الحجبُ في الخدمة فيُفحص على الشاشة الفعليّة وعلى PDF الناتج لا على القالب وحده.
"""

import io

import pdfplumber
import pytest
from django.core.exceptions import PermissionDenied

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
        result = build_followup_pdf(school, user, {"date": DAY})
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
        body = _get(client_as, staff[role]).content.decode()
        assert ">متابعةُ التواصل</th>" in body and ">متابعةُ الإجراء</th>" in body
        assert _pdf_marks(staff[role], school) >= _pdf_marks(supervisor, school) + 2

    def test_the_wing_supervisor_and_academic_deputy_get_none_of_it(
        self, client_as, staff, supervisor, absent_both, school
    ):
        _seed_status(client_as, staff["principal"], absent_both[0])
        for user in (supervisor, staff["vice_academic"]):
            body = _get(client_as, user).content.decode()
            assert ">متابعةُ التواصل</th>" not in body and ">متابعةُ الإجراء</th>" not in body
            rows = svc.followup_rows(user, SUNDAY)
            assert all(r["contact_status"] == "" and r["action_status"] == "" for r in rows)
            assert _pdf_marks(user, school) in (None, _pdf_marks(supervisor, school))

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
        body = _get(client_as, staff["principal"]).content.decode()
        assert "تحويل لمنسق شؤون الطلاب" in body and "تحويل للأخصائي الاجتماعي" in body
        assert "إشعار كتابي" not in body and "تعهد خطي" in body

    def test_an_old_written_notice_row_reads_as_a_pledge_unchanged(
        self, client_as, staff, absent_both
    ):
        _post_action(client_as, staff["principal"], absent_both[0], action_kind="written_notice")
        row = AbsenceActionLog.objects.get()
        assert row.action_kind == "written_notice"
        assert row.get_action_kind_display() == "تعهد خطي"
        assert "تعهد خطي" in _get(client_as, staff["principal"]).content.decode()


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
