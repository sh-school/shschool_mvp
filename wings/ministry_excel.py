"""«إحصائية الغياب» في Excel — بأدوات المنصّة المشتركة (ترويسةٌ واحدة، ورقةٌ محميّةٌ للقراءة)."""

from __future__ import annotations

from core import brand
from core.excel_safety import safe_cell
from core.export_utils import add_excel_title_rows, excel_table_styles, xl_fill, xl_font
from core.ministry import ministry_line, ministry_name
from reports.services import ExcelService

from .absence_stats import TABLE_COLUMNS, AbsenceStats, absence_stats
from .ministry_selectors import MinistrySummary
from .register_excel import CENTER, HEADER_ROW, START, _setup_page

#: عرضُ أعمدة الورقة الأولى: الاسمُ ثمّ المقيدون والحاضرون والغائبون والنسبة.
WIDTHS = (24, 14, 14, 14, 14)


def _values(line) -> list:
    """صفُّ جدولٍ بالأعمدة الخمسة: الاسم، المقيدون، الحاضرون، الغائبون، نسبة الغياب."""
    return [line.label, line.enrolled, line.present, line.absent_both, f"{line.rate}%"]


def _write_row(ws, row: int, values: list, table, *, bold: bool = False, fill: str | None = None):
    for col, value in enumerate(values, start=1):
        cell = safe_cell(ws, row=row, column=col, value=value)
        cell.border = table.border
        cell.alignment = START if col == 1 else CENTER
        cell.font = xl_font(brand.MAROON, bold=True) if bold else table.cell_font
        if fill:
            cell.fill = xl_fill(fill)
    ws.row_dimensions[row].height = 20


def _write_section(ws, row: int, title: str, headers: list[str], lines: list, table) -> int:
    """عنوانُ قسمٍ ثمّ رأسُ جدولٍ ثمّ سطورُه؛ يعيد آخرَ صفٍّ كُتب."""
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=len(WIDTHS))
    cell = safe_cell(ws, row=row, column=1, value=title)
    cell.font = xl_font(brand.MAROON, bold=True)
    cell.alignment = START
    row += 1
    ExcelService._add_header_row(
        ws,
        {
            "header_font": table.header_font,
            "header_fill": table.header_fill,
            "header_align": table.header_align,
            "thin_border": table.border,
        },
        row,
        list(zip(headers, WIDTHS, strict=True)),
    )
    for line in lines:
        row += 1
        _write_row(ws, row, _values(line), table)
    return row


def ministry_workbook(
    summary: MinistrySummary,
    school_name: str,
    exported_by: str,
    orientation: str = "landscape",
    stats: AbsenceStats | None = None,
):
    """ورقتان: «إحصائية الغياب» (إجمالي المدرسة ثمّ الشعب فالأجنحة فالمراحل)، ثمّ أسماءُ من يُرفعون غائبين."""
    stats = stats or absence_stats(summary)
    wb, ws, _ = ExcelService._make_workbook("إحصائية الغياب")
    ws.sheet_view.rightToLeft = True
    table = excel_table_styles()
    num_cols = len(WIDTHS)
    add_excel_title_rows(
        ws,
        num_cols,
        ministry_line(school_name, ministry_name(short=True), sep="  —  "),
        f"إحصائية الغياب  —  {summary.day:%Y/%m/%d}",
        f"الطلاب الغائبون في الحصة الأولى والثانية  |  صدر بواسطة: {exported_by}",
    )
    tables = stats.tables
    row = _write_section(
        ws,
        HEADER_ROW,
        "الإحصائية الإجمالية على مستوى المدرسة",
        ["النطاق", *TABLE_COLUMNS],
        [stats.school],
        table,
    )
    for item in tables:
        row = _write_section(
            ws, row + 2, f"نسب الغياب — {item.title}", item.headers, item.lines, table
        )
    for note in summary.notes:
        row += 1
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=num_cols)
        cell = safe_cell(ws, row=row, column=1, value=note)
        cell.font = xl_font(brand.STATUS_WARNING_DARK, size=9, bold=True)
        cell.alignment = START
    _setup_page(ws, num_cols, row, school_name, orientation)
    ExcelService._apply_protection(ws, num_cols)

    names = wb.create_sheet("للرفع في نظام الوزارة")
    names.sheet_view.rightToLeft = True
    add_excel_title_rows(
        names,
        3,
        ministry_line(school_name, ministry_name(short=True), sep="  —  "),
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
            cell = safe_cell(names, row=last, column=col, value=value)
            cell.border = table.border
            cell.alignment = START if col == 1 else CENTER
            cell.font = table.cell_font
            cell.fill = xl_fill(brand.grade_tint(item.grade))
    _setup_page(names, 3, last, school_name, orientation)
    ExcelService._apply_protection(names, 3)
    return wb
