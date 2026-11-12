"""فصلُ متابعة الغياب إلى صفحتين مستقلّتين (W-20261017-024).

التواصلُ مع الأولياء (تسعة أعمدة) ومتابعةُ الإجراءات (ثمانية)، والمتابعةُ والطباعةُ لثلاثة أدوارٍ فرضاً في الخادم،
وملفُّ PDF بالاتّجاهين بآليّة الزيارة الصفّية، بلا زرّ مشاركة.
"""

import io
from types import SimpleNamespace

import pdfplumber
import pytest
from django.urls import reverse

from operations.absence_followup_print import sheets_of
from operations.models import AbsenceActionLog
from operations.services import absence_followup as svc
from tests.operations.test_absence_followup import (  # noqa: F401
    _calendar_first,
    _get,
    _post_action,
    absent_both,
    second_wing,
    staff,
)
from tests.test_period_register import (  # noqa: F401
    SUNDAY,
    kids,
    klass,
    other_teacher,
    subjects,
    supervisor,
    teacher,
    year,
)

pytestmark = pytest.mark.django_db

THREE = ("principal", "vice_admin", "coordinator")
PRINT_URL = "absence_followup_print"


def _head(body: str) -> str:
    return body[body.index("<thead>") : body.index("</thead>")]


class TestTwoPages:
    def test_the_old_path_is_the_contact_page_and_the_actions_page_is_separate(
        self, client_as, staff, absent_both
    ):
        contact = _get(client_as, staff["principal"]).content.decode()
        actions = _get(client_as, staff["principal"], "absence_actions").content.decode()
        assert reverse("daily_report") == "/teacher/reports/daily/"
        assert "هاتفُ وليّ الأمر" in contact and "الإجراءُ الحاليّ" not in contact
        assert "الإجراءُ الحاليّ" in actions and "هاتفُ وليّ الأمر" not in actions

    def test_contact_has_nine_columns_without_follow_up_columns(
        self, client_as, staff, absent_both
    ):
        body = _get(client_as, staff["principal"]).content.decode()
        assert _head(body).count("<th ") == 9
        assert "متابعةُ التواصل" not in body and "وقتُ المتابعة" not in body

    def test_actions_has_nine_columns_for_the_three_and_fewer_for_a_supervisor(
        self, client_as, staff, supervisor, absent_both
    ):
        body = _get(client_as, staff["principal"], "absence_actions").content.decode()
        head = _head(body)
        # تسعةُ أعمدةٍ بعد إضافة «أيام الغياب» (W-20261107-018)
        assert head.count("<th ") == 9
        assert "متابعةُ الإجراء" in head and "وقتُ المتابعة ومن سجّلها" in head
        mine = _get(client_as, supervisor, "absence_actions").content.decode()
        assert "متابعةُ الإجراء" not in mine and "وقتُ المتابعة" not in mine


class TestFollowUpStamp:
    def test_an_empty_follow_up_reads_not_followed_up(self, client_as, staff, absent_both):
        body = _get(client_as, staff["principal"], "absence_actions").content.decode()
        assert "لم تتمّ المتابعة" in body

    def test_recording_a_follow_up_stamps_time_and_recorder_only_for_the_three(
        self, client_as, staff, supervisor, absent_both
    ):
        kid = absent_both[0]
        _post_action(client_as, supervisor, kid, status="")
        first = AbsenceActionLog.objects.get()
        assert first.followed_at is None and first.followed_by is None
        _post_action(client_as, staff["vice_admin"], kid, status="partial", corrects=str(first.id))
        head = AbsenceActionLog.objects.filter(corrects__isnull=False).get()
        assert head.status == "partial" and head.followed_by == staff["vice_admin"]
        assert head.followed_at is not None
        assert head.acted_by == supervisor, "المنفِّذ الأصليّ لا يتبدّل بتسجيل المتابعة"
        row = svc.followup_rows(staff["principal"], SUNDAY)[0]
        assert row["followed_by"] == staff["vice_admin"].full_name
        hidden = svc.followup_rows(supervisor, SUNDAY)[0]
        assert hidden["followed_at"] is None and hidden["followed_by"] is None


class TestPrintIsServerSide:
    @pytest.mark.parametrize("name", [PRINT_URL, "absence_followup_pdf"])
    def test_only_the_three_may_open_the_print_routes(
        self, client_as, staff, supervisor, teacher, absent_both, name
    ):
        for user in (supervisor, staff["vice_academic"], teacher):
            assert _get(client_as, user, name).status_code == 403
        for role in THREE:
            assert _get(client_as, staff[role], name).status_code == 200

    def test_the_buttons_are_hidden_from_everyone_else(
        self, client_as, staff, supervisor, absent_both
    ):
        for user in (supervisor, staff["vice_academic"]):
            for name in ("daily_report", "absence_actions"):
                body = _get(client_as, user, name).content.decode()
                assert (
                    reverse(PRINT_URL) not in body and reverse("absence_followup_pdf") not in body
                )
        # زرُّ PDF يمرّ بنقطة الملفّ (تنزيلٌ مسجَّل) لا بصفحة المعاينة (W-20261021-005)
        assert (
            reverse("absence_followup_pdf") in _get(client_as, staff["principal"]).content.decode()
        )

    @pytest.mark.parametrize(
        ("page", "default"), [("contact", "landscape"), ("actions", "landscape")]
    )
    def test_the_pdf_follows_the_orientation_with_a_per_page_default(
        self, client_as, staff, absent_both, page, default
    ):
        def size(**extra):
            resp = _get(client_as, staff["principal"], "absence_followup_pdf", page=page, **extra)
            assert resp["Content-Type"] == "application/pdf" and resp.content[:4] == b"%PDF"
            assert resp["Content-Disposition"].startswith("inline")
            first = pdfplumber.open(io.BytesIO(resp.content)).pages[0]
            return "landscape" if first.width > first.height else "portrait"

        assert size() == default
        assert size(orient="portrait") == "portrait"
        assert size(orient="landscape") == "landscape"
        assert size(orient="diagonal") == default

    def test_the_viewer_is_an_iframe_page_without_a_share_button(
        self, client_as, staff, absent_both
    ):
        body = _get(client_as, staff["principal"], PRINT_URL, page="actions").content.decode()
        assert "site-nav" in body and "<iframe" in body and 'name="orient"' in body
        assert "download" in body and "مشاركةُ نسخة" not in body and "رجوع" in body
        assert reverse("absence_followup_pdf") in body

    def test_the_download_is_an_attachment_and_leaves_an_audit_row_with_counts_only(
        self, client_as, staff, absent_both
    ):
        from core.models import AuditLog

        resp = _get(client_as, staff["principal"], "absence_followup_pdf", download=1)
        assert resp["Content-Disposition"].startswith("attachment")
        row = AuditLog.objects.filter(action="export").order_by("-timestamp").first()
        assert "absence_followup" in str(row.changes) and "طالب" not in str(row.changes)

    def test_the_pdf_has_no_guardian_name(self, client_as, staff, absent_both):
        resp = _get(client_as, staff["principal"], "absence_followup_pdf", page="contact")
        pages = pdfplumber.open(io.BytesIO(resp.content)).pages
        text = " ".join(p.extract_text() or "" for p in pages)
        assert "اسم ولي" not in text and "اسم الأم" not in text


def _pages(resp) -> list[str]:
    return [p.extract_text() or "" for p in pdfplumber.open(io.BytesIO(resp.content)).pages]


def _shows(text: str, phrase: str) -> bool:
    """pdfplumber يُرجع العربيّةَ أحياناً معكوسةً (كعدّ «متابعة» في كشف الأعمدة)، فيُقبل الاتجاهان."""
    return phrase in text or phrase[::-1] in text


class TestSheetsPerClass:
    def test_sheets_group_by_class_in_grade_then_section_and_skip_empty_classes(self):
        a = SimpleNamespace(id=1, grade="G8", section="2", short_label="8/2")
        b = SimpleNamespace(id=2, grade="G8", section="1", short_label="8/1")
        rows = [{"class_group": a, "n": 1}, {"class_group": b, "n": 2}, {"class_group": a, "n": 3}]
        sheets = sheets_of(rows)
        assert [s["label"] for s in sheets] == ["8/1", "8/2"]
        assert [len(s["rows"]) for s in sheets] == [1, 2]
        assert [(s["no"], s["total"]) for s in sheets] == [(1, 2), (2, 2)]
        assert sheets_of([]) == []

    def test_without_the_option_the_pdf_is_one_sheet_without_heads(
        self, client_as, staff, absent_both
    ):
        resp = _get(client_as, staff["principal"], "absence_followup_pdf", page="contact")
        pages = _pages(resp)
        assert len(pages) == 1 and not _shows(pages[0], "ورقة")

    def test_with_the_option_each_class_with_absences_starts_its_own_numbered_sheet(
        self, client_as, staff, absent_both
    ):
        resp = _get(
            client_as, staff["principal"], "absence_followup_pdf", page="contact", split="class"
        )
        assert resp.content[:4] == b"%PDF"
        pages = _pages(resp)
        assert len(pages) == 2
        assert _shows(pages[0], "ورقة 1 من 2") and _shows(pages[1], "ورقة 2 من 2")

    def test_the_wing_supervisor_sheets_hold_only_his_own_class(
        self, supervisor, klass, second_wing, absent_both
    ):
        # مشرفُ الجناح لا يملك قدرةَ الطباعة (THREE وحدها)، فيُختبر النطاقُ عند محدِّد الصفوف الذي يغذّي PDF وExcel معاً.
        from operations.export_tables import shown_rows

        params = {"date": SUNDAY.isoformat(), "split": "class"}
        sheets = sheets_of(shown_rows(supervisor, params))
        assert [s["label"] for s in sheets] == [klass.short_label]
        assert sheets[0]["no"] == 1 and sheets[0]["total"] == 1

    def test_the_viewer_offers_the_per_class_toggle_and_carries_it_to_the_pdf(
        self, client_as, staff, absent_both
    ):
        body = _get(client_as, staff["principal"], PRINT_URL, page="contact").content.decode()
        assert "كل صف في ورقة" in body and "split=class" in body
        on = _get(
            client_as, staff["principal"], PRINT_URL, page="contact", split="class"
        ).content.decode()
        assert "الكشف الموحَّد" in on and "split=class" in on
