"""[BRAND] رؤيةُ الوزارة في ذيل الطباعة لكلّ ملفّ Excel مصدَّر بلا استثناء (قرارُ المالك 2026-09-27).

كانت ملفّاتُ الـPDF تحملها في تذييلها وملفّاتُ Excel تُطبع بـ«صفحة / عدد» والتاريخ فقط. فالمساعدُ الواحد `core.export_utils.apply_print_footer` يضع الرؤيةَ من مصدرها الواحد
(`components/ministry_vision.html` عبر `core.ministry_vision`) في السطر الأعلى من ذيل كلّ ورقة، وتستدعيه **كلُّ نقطة حفظٍ** لمصنّف. والحارسُ النصّيّ يمنع نقطةَ حفظٍ جديدةً بلا الرؤية.
"""

import io
import pathlib
import re

import openpyxl
import pytest
from django.urls import reverse

from core.export_utils import apply_print_footer, excel_to_response
from core.ministry_vision import ministry_vision_text
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
VISION = "مُتَعَلِّمٌ رِيَادِيٌّ لِتَنْمِيَةٍ مُسْتَدَامَةٍ"


def _workbook(sheets=2):
    wb = openpyxl.Workbook()
    wb.active.title = "أ"
    for i in range(sheets - 1):
        wb.create_sheet(f"ب{i}")
    return wb


def _footer_of(ws):
    return ws.oddFooter.center.text or ""


def test_the_vision_text_comes_from_the_single_partial_without_markup():
    text = ministry_vision_text()
    assert text == VISION and "<" not in text


def test_every_sheet_gets_the_vision_above_the_page_counter_and_keeps_the_date():
    wb = _workbook(3)
    apply_print_footer(wb)
    for ws in wb.worksheets:
        lines = _footer_of(ws).split("\n")
        assert lines == [VISION, "&P / &N"], lines
        assert ws.oddFooter.right.text == "&D"
        assert ws.page_margins.bottom >= 0.75, "سطران في الذيل يلزمهما هامشٌ سفليٌّ"


def test_a_sheet_that_already_had_a_footer_does_not_lose_its_right_side():
    wb = _workbook(1)
    wb.active.oddFooter.right.text = "&D &T"
    wb.active.oddFooter.center.text = "&P / &N"
    apply_print_footer(wb)
    assert wb.active.oddFooter.right.text == "&D &T"
    assert _footer_of(wb.active).startswith(VISION)


def test_the_schools_own_vision_wins_over_the_default(school):
    school.vision = "رؤيةٌ خاصّةٌ بهذه المدرسة"
    wb = _workbook(1)
    apply_print_footer(wb, school)
    assert _footer_of(wb.active).split("\n")[0] == "رؤيةٌ خاصّةٌ بهذه المدرسة"


def test_the_response_helper_stamps_it_into_the_downloaded_file():
    response = excel_to_response(_workbook(2), "x.xlsx")
    saved = openpyxl.load_workbook(io.BytesIO(response.content))
    assert all(_footer_of(ws).startswith(VISION) for ws in saved.worksheets)


@pytest.mark.django_db
def test_the_real_student_export_carries_the_vision_in_its_print_footer(
    client_as, principal_user, school, seeded_calendar
):
    klass = ClassGroupFactory(school=school, academic_year=seeded_calendar)
    student = UserFactory(full_name="طالبٌ للاختبار", national_id="99900000123")
    MembershipFactory(user=student, school=school, role=RoleFactory(school=school, name="student"))
    StudentEnrollmentFactory(student=student, class_group=klass)

    response = client_as(principal_user).get(reverse("student_affairs:student_export"))
    assert response.status_code == 200
    ws = openpyxl.load_workbook(io.BytesIO(response.content)).active
    assert _footer_of(ws).split("\n")[0] == ministry_vision_text(school)


# ── الحارس النصّيّ: لا نقطةَ حفظٍ لمصنّفٍ بلا الرؤية ─────────────────────────────────────────────────────────

#: حفظُ مصنّفٍ إلى بايتات — `wb.save(buf)`، أو `schedule_workbook(ctx).save(buffer)`.
_SAVE = re.compile(r"\.save\((?:buf|buffer|output)\)")
_CREATE = re.compile(r"\b(?:openpyxl\.)?Workbook\(\)")
#: ما يستدعي المساعدَ في مسار الحفظ.
_HELPERS = ("apply_print_footer(", "excel_to_response(", "_wb_to_response(", ".to_response(")

#: مصنّفاتٌ تُنشأ في مكانٍ وتُحفظ في آخر — مع سببها.
CREATED_ELSEWHERE_SAVED_THROUGH_A_HELPER = {
    "staff_affairs/attendance/daily.py": "يُحفظ عبر `excel_to_response` في `staff_affairs/views_attendance.py`",
}


def _sources():
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if (
            rel.startswith(("tests/", ".claude/", "venv/", ".venv/", "node_modules/", "static/"))
            or "/migrations/" in rel
            or "/management/commands/" in rel
        ):
            continue
        yield rel, path.read_text(encoding="utf-8", errors="ignore")


def test_every_workbook_save_point_stamps_the_vision_first():
    """كلُّ ملفٍّ فيه حفظُ مصنّفٍ إلى بايتات يستدعي `apply_print_footer` (أو ما يستدعيه) — وإلّا خرج مصنّفٌ بلا الرؤية."""
    missing = [
        rel for rel, src in _sources() if _SAVE.search(src) and "apply_print_footer(" not in src
    ]
    assert (
        not missing
    ), f"نقطةُ حفظ مصنّفٍ بلا `apply_print_footer` (رؤيةُ الوزارة في ذيل الطباعة): {missing}"


def test_every_workbook_creator_saves_through_a_stamping_helper():
    missing = []
    for rel, src in _sources():
        if not _CREATE.search(src) or rel in CREATED_ELSEWHERE_SAVED_THROUGH_A_HELPER:
            continue
        if not any(h in src for h in _HELPERS):
            missing.append(rel)
    assert not missing, f"مصنّفٌ يُنشأ بلا مسارِ حفظٍ يختم الرؤية: {missing}"


def test_the_creator_exceptions_are_real_and_still_needed():
    for rel in CREATED_ELSEWHERE_SAVED_THROUGH_A_HELPER:
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert _CREATE.search(src), f"{rel} لم يعد يُنشئ مصنّفاً — احذفه من الاستثناءات"
