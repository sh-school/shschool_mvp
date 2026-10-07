"""ملخّصُ الحصّتين الأولى والثانية في Excel — بأدوات المنصّة المشتركة (ترويسةٌ واحدة، ورقةٌ محميّةٌ للقراءة)."""

from __future__ import annotations

from core import brand
from core.export_utils import add_excel_title_rows, excel_table_styles, xl_fill, xl_font
from reports.services import ExcelService

from .ministry_selectors import MinistrySummary
from .register_excel import CENTER, HEADER_ROW, START, _setup_page

COLUMNS = (
    ("الصفّ / الشعبة", 18),
    ("المقيَّدون", 11),
    ("غابوا الحصّتين بلا عذر", 14),
    ("غابوا الحصّتين بعذر", 14),
    ("غابوا إحداهما", 12),
    ("تأخّروا", 10),
    ("بلا رصد", 10),
    ("بانتظار الاعتماد", 12),
)


def _values(label: str, counts) -> list:
    return [
        label,
        counts.enrolled,
        counts.absent_both_unexcused,
        counts.absent_both_excused,
        counts.absent_one,
        counts.late,
        counts.unrecorded,
        counts.pending,
    ]


def _write_row(ws, row: int, values: list, table, *, bold: bool = False, fill: str | None = None):
    for col, value in enumerate(values, start=1):
        cell = ws.cell(row=row, column=col, value=value)
        cell.border = table.border
        cell.alignment = START if col == 1 else CENTER
        cell.font = xl_font(brand.MAROON, bold=True) if bold else table.cell_font
        if fill:
            cell.fill = xl_fill(fill)
    ws.row_dimensions[row].height = 20


def ministry_workbook(
    summary: MinistrySummary,
    school_name: str,
    exported_by: str,
    orientation: str = "landscape",
):
    """ورقتان: الملخّصُ بالشعبة والصفّ والمدرسة، ثمّ أسماءُ من يُرفعون غائبين."""
    wb, ws, _ = ExcelService._make_workbook("ملخّص الحصّتين")
    ws.sheet_view.rightToLeft = True
    table = excel_table_styles()
    num_cols = len(COLUMNS)
    add_excel_title_rows(
        ws,
        num_cols,
        f"{school_name}  —  وزارة التربية والتعليم والتعليم العالي",
        f"ملخّصُ غياب الحصّتين الأولى والثانية  —  {summary.day:%Y/%m/%d}",
        f"للرفع في نظام الوزارة يدويّاً  |  صدر بواسطة: {exported_by}",
    )
    ExcelService._add_header_row(
        ws,
        {
            "header_font": table.header_font,
            "header_fill": table.header_fill,
            "header_align": table.header_align,
            "thin_border": table.border,
        },
        HEADER_ROW,
        list(COLUMNS),
    )
    ws.row_dimensions[HEADER_ROW].height = 34
    row = HEADER_ROW
    for grade in summary.grades:
        for item in grade.rows:
            row += 1
            label = item.group.short_code + ("" if item.has_periods else "  (لا حصّتان)")
            _write_row(ws, row, _values(label, item.counts), table)
        row += 1
        _write_row(
            ws, row, _values(f"مجموع {grade.label}", grade.counts), table, bold=True,
            fill=brand.MAROON_BG,
        )  # fmt: skip
    row += 1
    _write_row(
        ws, row, _values("مجموع المدرسة", summary.total), table, bold=True, fill=brand.MAROON_BG
    )
    for note in summary.notes:
        row += 1
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=num_cols)
        cell = ws.cell(row=row, column=1, value=note)
        cell.font = xl_font(brand.STATUS_WARNING_DARK, size=9, bold=True)
        cell.alignment = START
    ws.freeze_panes = ws.cell(row=HEADER_ROW + 1, column=2)
    _setup_page(ws, num_cols, row, school_name, orientation)
    ExcelService._apply_protection(ws, num_cols)

    names = wb.create_sheet("للرفع في نظام الوزارة")
    names.sheet_view.rightToLeft = True
    add_excel_title_rows(
        names,
        3,
        f"{school_name}  —  وزارة التربية والتعليم والتعليم العالي",
        f"من غاب الحصّتين الأولى والثانية  —  {summary.day:%Y/%m/%d}",
        f"العددُ: {len(summary.ministered)}  |  صدر بواسطة: {exported_by}",
    )
    ExcelService._add_header_row(
        names,
        {
            "header_font": table.header_font,
            "header_fill": table.header_fill,
            "header_align": table.header_align,
            "thin_border": table.border,
        },
        HEADER_ROW,
        [("الطالب", 40), ("الشعبة", 14), ("الحال", 16)],
    )
    last = HEADER_ROW
    for item in summary.ministered:
        last += 1
        for col, value in enumerate(
            (item.name, item.class_code, "غائب بعذر" if item.excused else "غائب بلا عذر"), start=1
        ):
            cell = names.cell(row=last, column=col, value=value)
            cell.border = table.border
            cell.alignment = START if col == 1 else CENTER
            cell.font = table.cell_font
    _setup_page(names, 3, last, school_name, orientation)
    ExcelService._apply_protection(names, 3)
    return wb
