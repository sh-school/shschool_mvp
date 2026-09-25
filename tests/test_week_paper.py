"""الجدولُ الأسبوعيّ الديناميكيّ (3/3): الورقةُ المطبوعة وPDF وExcel تتبع الأسبوعَ الفعليّ (2026-09-25).

الصفحةُ صارت تعرض الأسبوعَ الفعليّ بأيّامه المغلقة وحصصه المحوَّلة (2/3)؛ وهذا الطلبُ يُدخل ما فيها في
الورق: ترويسةٌ بنطاق الأسبوع، وخانةٌ ملوَّنةٌ فيها «عن فلان»، ومفتاحُ ألوانٍ وملاحظاتٌ أسفل الجدول — ولملفّ
Excel كذلك. والخطّةُ (الافتراضيّ للطباعة والتصدير) تبقى كما كانت حرفاً: لا نطاقَ ولا مفتاحَ ولا تغييرَ في
المقاس، فالمعلَّقُ في المدرسة لا يتبدّل من تحته.
"""

from io import BytesIO

import openpyxl
import pytest
from django.urls import reverse

from core import brand
from core.models import ExportJob
from operations.schedule_paper import cell_kind, paper_geometry
from operations.schedule_selectors import _week_notes
from operations.services import SubstituteService
from operations.services.schedule_week import WeekLessons
from tests.test_week_page import (  # noqa: F401 — `world` fixture مشتركةٌ مع اختبارات الصفحة
    BREAK_SUNDAY,
    SUNDAY,
    YEAR,
    _generate,
    world,
)

pytestmark = pytest.mark.django_db

RANGE = "11 أكتوبر – 15 أكتوبر 2026"
FUTURE = "2026-10-18"
INFO_FILL = brand.excel(brand.STATUS_INFO_BG)


def _swap(w):
    """حصّةُ المعلّم الأوّل يومَ الأحد بيدِ البديل — تبديلٌ في الأسبوع الجاري."""
    _generate(w)
    SubstituteService.hand_over_session(w["school"], w["s1"], SUNDAY, w["sub"])


def _paper(client, w, **params) -> str:
    client.force_login(w["principal"])
    return client.get(
        reverse("schedule_print"), {"year": YEAR, **params}, HTTP_HOST="localhost"
    ).content.decode()


def _sheet(client, w, **params):
    """ورقةُ Excel من مسار التصدير كاملاً: الطلبُ ثمّ المهمّةُ الخلفيّة (متزامنةٌ في الاختبارات)."""
    client.force_login(w["principal"])
    response = client.get(
        reverse("schedule_export_excel"),
        {"year": YEAR, **params},
        HTTP_HOST="localhost",
        follow=True,
    )
    return openpyxl.load_workbook(BytesIO(response.content)).active


def _texts(sheet) -> list[str]:
    return [str(c.value) for row in sheet.iter_rows() for c in row if c.value is not None]


def _fills(sheet) -> set[str]:
    return {
        c.fill.fgColor.rgb[-6:]
        for row in sheet.iter_rows()
        for c in row
        if c.fill is not None
        and c.fill.fill_type == "solid"
        and isinstance(c.fill.fgColor.rgb, str)
    }


class TestThePaperNamesItsWeek:
    def test_an_actual_paper_writes_the_week_range_in_its_header(self, world, client):
        actual = _paper(
            client,
            world,
            view="teacher",
            teacher=str(world["t1"].id),
            source="actual",
            week=str(SUNDAY),
        )
        plan = _paper(client, world, view="teacher", teacher=str(world["t1"].id))

        assert f"الأسبوع {RANGE}" in actual
        assert "الأسبوع 11 أكتوبر" not in plan, "ورقةُ الخطّة كما كانت: بلا نطاق"

    def test_the_general_schedule_paper_writes_it_too(self, world, client):
        body = _paper(client, world, view="all_teachers", source="actual", week=str(SUNDAY))

        assert f"الأسبوع {RANGE}" in body.split('class="sub"', 1)[1].split("</div>", 1)[0]

    def test_the_file_name_carries_the_week_only_for_an_actual_week(self, world, client):
        _sheet(
            client, world, view="teacher", teacher=str(world["t1"].id), source="actual", week=FUTURE
        )
        _sheet(client, world, view="teacher", teacher=str(world["t1"].id))

        names = list(ExportJob.objects.order_by("created_at").values_list("filename", flat=True))
        assert FUTURE in names[0] and "أسبوع" in names[0]
        assert "أسبوع" not in names[1] and FUTURE not in names[1]


class TestAMovedLessonOnPaper:
    def test_the_cell_is_coloured_explained_and_keyed(self, world, client):
        _swap(world)

        body = _paper(
            client,
            world,
            view="teacher",
            teacher=str(world["sub"].id),
            source="actual",
            week=str(SUNDAY),
        )

        assert "تبديل — كانت لـمعلّمٌ أوّل" in body, "«عن فلان» في الخانة نصّاً"
        assert ' wg-swap"' in body, "والخانةُ بصنفها"
        assert ".week-grid td.wg-swap" in body, "والورقةُ تعرّف لونَه في أنماطها هي لا في أنماط المنصّة"
        assert '<span class="week-legend__swatch is-swap"></span> تبديل' in body, "ومفتاحُه"

    def test_the_general_schedule_marks_the_cell_and_keys_it(self, world, client):
        _swap(world)

        body = _paper(client, world, view="all_teachers", source="actual", week=str(SUNDAY))

        assert ' mk-swap"' in body, "خانةُ الحصّة المحوَّلة"
        assert "matrix-legend__swatch mk-swap" in body, "ومفتاحُها"
        assert "تبديل — كانت لـمعلّمٌ أوّل" in body, "وتفسيرُها في بطاقة الخانة"

    def test_the_plan_paper_has_neither_mark_nor_strip(self, world, client):
        _swap(world)

        teacher = _paper(client, world, view="teacher", teacher=str(world["sub"].id))
        matrix = _paper(client, world, view="all_teachers")

        assert 'class="week-notes"' not in teacher and "تبديل — كانت" not in teacher
        assert ' mk-swap"' not in matrix and 'class="matrix-note"' not in matrix

    def test_the_cell_kind_reads_the_first_moved_lesson(self):
        class Lesson:
            def __init__(self, kind=""):
                self.kind = kind

        assert cell_kind([Lesson(), Lesson("cover"), Lesson("swap")]) == "cover"
        assert cell_kind([Lesson()]) == cell_kind([]) == cell_kind(None) == ""
        assert cell_kind([object()]) == "", "حصّةُ الخطّة بلا `kind` أصلاً"


class TestWhatTheWeekSaysAboutItself:
    def test_days_from_the_plan_are_named_under_the_grid(self, world, client):
        body = _paper(
            client, world, view="teacher", teacher=str(world["t2"].id), source="actual", week=FUTURE
        )

        strip = body.split('class="week-notes"', 1)[1]
        assert "لم تُولَّد حصصُ الأحد" in strip and "فتُعرض وفق الخطّة المعتمدة" in strip

    def test_a_holiday_week_says_why_on_the_general_paper(self, world, client):
        body = _paper(client, world, view="all_teachers", source="actual", week=str(BREAK_SUNDAY))

        assert "لا حصصَ في هذا الأسبوع" in body
        assert "إجازة منتصف الفصل الأول" in body.split('class="matrix-note"', 1)[1]

    def test_the_notes_are_whole_sentences_and_group_days_by_reason(self):
        week = WeekLessons(
            week_start=BREAK_SUNDAY,
            days=[],
            closed={0: "إجازة", 1: "إجازة", 2: "عيد"},
            plan_days={3, 4},
            unplaced=2,
        )

        assert _week_notes(week) == [
            "الأحد، الاثنين: إجازة؛ الثلاثاء: عيد — لا حصص.",
            "لم تُولَّد حصصُ الأربعاء، الخميس بعد، فتُعرض وفق الخطّة المعتمدة.",
            "2 حصّةً تاريخيّةً بلا رقمٍ (من جدولٍ سابق) لا تُعرض.",
        ]
        assert _week_notes(None) == []

    def test_the_strip_takes_its_lines_from_the_rows_not_from_the_sheet(self):
        bare = paper_geometry("a4", "landscape", with_who=False)
        keyed = paper_geometry("a4", "landscape", with_who=False, strip_lines=3)

        assert bare.notes_h == 0 and keyed.notes_h > 0
        assert keyed.row_h < bare.row_h
        # الورقةُ صفحةٌ واحدة: ما أُخذ للشريط أُخذ من الصفوف لا من الهامش.
        assert keyed.bands_h + keyed.row_h * keyed.rows <= keyed.content_h + 0.5


class TestExcelFollowsTheWeek:
    def test_a_teacher_sheet_has_the_range_the_note_the_colour_and_the_key(self, world, client):
        _swap(world)

        sheet = _sheet(
            client,
            world,
            view="teacher",
            teacher=str(world["sub"].id),
            source="actual",
            week=str(SUNDAY),
        )
        texts = _texts(sheet)

        assert any(RANGE in t for t in texts), "نطاقُ الأسبوع في العنوان"
        assert any("تبديل — كانت لـمعلّمٌ أوّل" in t for t in texts), "«عن فلان» في الخانة"
        assert INFO_FILL in _fills(sheet), "والخانةُ ملوَّنةٌ كالورقة"
        assert "تبديل" in texts, "ومفتاحُ اللون تحت الجدول"

    def test_the_general_sheet_colours_the_moved_cell_and_lists_the_key(self, world, client):
        _swap(world)

        sheet = _sheet(client, world, view="all_teachers", source="actual", week=str(SUNDAY))

        assert INFO_FILL in _fills(sheet)
        assert "تبديل" in _texts(sheet)
        assert any(RANGE in t for t in _texts(sheet))

    def test_the_notes_are_rows_inside_the_print_area(self, world, client):
        sheet = _sheet(
            client, world, view="teacher", teacher=str(world["t2"].id), source="actual", week=FUTURE
        )

        note_rows = [
            c.row
            for row in sheet.iter_rows()
            for c in row
            if "فتُعرض وفق الخطّة المعتمدة" in str(c.value or "")
        ]
        assert note_rows, "ملاحظةُ أيّام الخطّة في الملفّ"
        assert int(sheet.print_area.split("$")[-1]) >= max(note_rows)

    def test_the_plan_sheet_is_what_it_was(self, world, client):
        _swap(world)

        sheet = _sheet(client, world, view="teacher", teacher=str(world["sub"].id))

        assert INFO_FILL not in _fills(sheet)
        assert not any("الأسبوع" in t and "أكتوبر" in t for t in _texts(sheet))
        assert sheet.max_row == 9, "عنوانٌ ورأسٌ وخمسةُ أيّامٍ لا مفتاحَ بعدها"
