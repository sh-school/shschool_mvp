"""operations/schedule_export.py — الجدولُ ورقةَ Excel.

الورقةُ هنا صورةُ المطبوعة لا مستودعُ بيانات: الشكلُ نفسه — القسمُ ثمّ المعلّم
ثمّ خمسةٌ وثلاثون خانةً ثمّ النصاب — كي يجد من فتح الملفّ ما رآه في الورق. ومن
أراد البيانات خاماً فله واجهةُ الإسناد لا هذا الملفّ.

والأنماطُ من `reports.services.ExcelService`: هي أنماطُ المنصّة كلّها — رأسٌ من
ثلاثة سطورٍ وشعارٌ وحمايةٌ وإعدادُ طباعة — وبناءُ نسخةٍ ثانيةٍ منها هنا يفرّق
ملفّات المدرسة على شكلين. والاستيرادُ داخل الدوال لأنّ `reports` تستورد
`operations.models`، فاستيرادٌ في رأس الملفّ يعقد الحلقة.
"""

from __future__ import annotations

from core import brand
from operations.schedule_paper import cell_kind

#: عرضُ خانة الحصّة: رمزُ الشعبة أربعةُ محارف («11/2») لا أكثر.
_CELL_WIDTH = 4.6

#: شريطُ القسم: الأقسامُ المتجاورة تتناوب على لونين فاتحين — فالحدُّ بينها
#: يُرى دون أن تُنسخ لوحةُ ألوان الورقة المطبوعة في موضعٍ ثانٍ تشيخ فيه.
_BAND_FILL = brand.excel(brand.MAROON_BG)

#: تلوينُ الحصّة المحوَّلة (أسبوعٌ فعليّ) — ألوانُ الورقة المطبوعة نفسُها (`week_grid_css.html`).
_KIND_FILL = {
    "cover": brand.excel(brand.STATUS_WARNING_BG),
    "swap": brand.excel(brand.STATUS_INFO_BG),
    "comp": brand.excel(brand.STATUS_SUCCESS_BG),
}

#: خطُّ المنصّة — هو خطُّ الشاشة والورقة، فليكن خطَّ الملفّ. وأنماطُ
#: `ExcelService` مكتوبةٌ بـArial، فتُمرّ الورقةُ بعد بنائها ويُبدَّل الاسمُ
#: وحدَه: الوزنُ واللونُ والحجمُ كما ضُبطت. ومن لم يكن الخطُّ على جهازه
#: أبدله Excel بأقرب موجود — ولا تسقط الورقة.
_FONT = "Tajawal"


def schedule_workbook(ctx: dict):
    """مُصنَّفُ Excel للورقة المعروضة — الجدولُ العام مصفوفةً، وما سواه شبكة."""
    if ctx.get("view_type") == "all_teachers":
        workbook = _matrix_workbook(ctx)
    else:
        workbook = _grid_workbook(ctx)
    _apply_font(workbook.active)
    return workbook


def _apply_font(ws) -> None:
    """خطُّ المنصّة على كلّ خانةٍ مكتوبة — بقيّةُ النمط كما هي."""
    from copy import copy

    for row in ws.iter_rows():
        for cell in row:
            if cell.font is not None and cell.font.name != _FONT:
                font = copy(cell.font)
                font.name = _FONT
                cell.font = font


def _sheet(title: str, report_title: str, ctx: dict, num_cols: int):
    """ورقةٌ برأس المنصّة الثلاثيّ — وتُعاد مع أنماطها لمن يملؤها.

    وفي الأسبوع الفعليّ يحمل العنوانُ نطاقَ الأسبوع، كترويسة الورقة المطبوعة.
    """
    from reports.services import ExcelService

    wb, ws, styles = ExcelService._make_workbook(title)
    school = ctx.get("school")
    nav = ctx.get("nav") or {}
    if ctx.get("source") == "actual" and nav.get("range"):
        report_title = f"{report_title} — الأسبوع {nav['range']}"
    ExcelService._add_professional_header(
        ws,
        school.name if school else "SchoolOS",
        report_title,
        ctx.get("year") or "",
        num_cols,
    )
    return wb, ws, styles


def _mark_moved(ws, row: int, column: int, kind: str) -> None:
    """يلوّن خانةَ حصّةٍ حُوّل معلّمُها — ولا يفعل لغيرها."""
    from openpyxl.styles import PatternFill

    if kind in _KIND_FILL:
        ws.cell(row=row, column=column).fill = PatternFill("solid", fgColor=_KIND_FILL[kind])


def _legend_rows(ws, ctx: dict, first_row: int, num_cols: int) -> int:
    """مفتاحُ ألوان الحصص المحوَّلة وملاحظاتُ الأسبوع أسفل الجدول — آخرُ صفٍّ كُتب.

    ما وُجد في الأسبوع وحدَه من الأنواع، وملاحظاتُه بنصّها في الورقة المطبوعة (`week_nav`). والخطّةُ
    بلا مفتاحٍ ولا ملاحظات، فيُرجَع `first_row - 1` ولا يُكتب شيء.
    """
    from openpyxl.styles import Alignment

    nav = ctx.get("nav") or {}
    row = first_row
    for kind, label in nav.get("kinds") or []:
        _mark_moved(ws, row, 1, kind)
        ws.cell(row=row, column=1, value=label).alignment = Alignment(
            horizontal="center", vertical="center"
        )
        row += 1
    for note in nav.get("notes") or []:
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=num_cols)
        ws.cell(row=row, column=1, value=note).alignment = Alignment(
            horizontal="right", vertical="center", wrap_text=True
        )
        ws.row_dimensions[row].height = 16
        row += 1
    return row - 1


def _matrix_row(
    ws, styles: dict, row_data: dict, row_num: int, band: bool, layout: tuple[int, int, int]
) -> None:
    """سطرُ معلّمٍ في الجدول العام: قسمُه واسمُه وحصصُه ونصابُه، بلون شريط قسمه ثمّ علامةِ ما حُوّل.

    `layout`: (أوّلُ عمودِ حصّة، عددُ الحصص في اليوم، عددُ الأعمدة). و`band`: شريطُ القسم الحاليّ.
    """
    from openpyxl.styles import Alignment, PatternFill

    from reports.services import ExcelService

    first_period_col, per_day, num_cols = layout
    span = row_data.get("dept_span") or 0
    if span:
        # قسمٌ بمعلّمٍ واحدٍ لا يُدمج: دمجُ خانةٍ بنفسها مدىً فارغُ المعنى
        # يبقى في الملفّ.
        if span > 1:
            ws.merge_cells(
                start_row=row_num, start_column=1, end_row=row_num + span - 1, end_column=1
            )
        ws.cell(row=row_num, column=1, value=row_data["department"]["name"])
    teacher = row_data.get("teacher")
    name_cell = ws.cell(row=row_num, column=2, value=getattr(teacher, "full_name", "") or "")
    name_cell.alignment = Alignment(horizontal="right", vertical="center")

    moved = []  # (عمود، نوع) لحصصٍ حُوّل معلّمُها — تُلوَّن بعد لون القسم لتغلبه
    for day_index, day in enumerate(row_data.get("days") or []):
        for period_index, cell in enumerate(day):
            column = first_period_col + day_index * per_day + period_index
            ws.cell(
                row=row_num,
                column=column,
                value=" ".join(slot.class_group.short_code for slot in cell),
            )
            if kind := cell_kind(cell):
                moved.append((column, kind))
    ws.cell(row=row_num, column=num_cols, value=row_data.get("total") or 0)

    ExcelService._style_data_row(ws, styles, row_num, num_cols, False)
    ws.row_dimensions[row_num].height = 17
    if band:
        fill = PatternFill("solid", fgColor=_BAND_FILL)
        for column in range(1, num_cols + 1):
            ws.cell(row=row_num, column=column).fill = fill
    for column, kind in moved:
        _mark_moved(ws, row_num, column, kind)
    # المحاذاةُ تُعاد بعد الأنماط: `_style_data_row` يوسّط كلّ خانة،
    # واسمُ المعلّم يُقرأ من يمينه.
    name_cell.alignment = Alignment(horizontal="right", vertical="center")
    ws.cell(row=row_num, column=1).alignment = Alignment(
        horizontal="center", vertical="center", wrap_text=True
    )


def _matrix_workbook(ctx: dict):
    """الجدول العام: سطرٌ لكلّ معلّم، والأسبوعُ خمسةٌ وثلاثون عموداً.

    والرأسُ سطران — الأيامُ مدموجةً فوق أرقام الحصص — كما في الورقة، فلا
    يقرأ أحدٌ رقم «٣» دون أن يعرف يومه.
    """
    from openpyxl.utils import get_column_letter

    from core.export_utils import xl_font
    from reports.services import ExcelService

    matrix = ctx.get("matrix") or []
    totals = ctx.get("matrix_totals")
    days = ctx.get("days") or []
    periods = list(ctx.get("period_numbers") or range(1, 8))

    first_period_col = 3
    num_cols = 2 + len(days) * len(periods) + 1
    wb, ws, styles = _sheet(
        "الجدول العام", ctx.get("title") or "الجدول العام للمعلمين", ctx, num_cols
    )

    # ── الرأس: سطرُ الأيام فوق سطر الحصص ──
    for column, header in ((1, "القسم"), (2, "المعلّم"), (num_cols, "النصاب")):
        letter = get_column_letter(column)
        ws.merge_cells(f"{letter}4:{letter}5")
        _head_cell(ws.cell(row=4, column=column, value=header), styles)

    column = first_period_col
    for _, day_name in days:
        span = len(periods)
        ws.merge_cells(start_row=4, start_column=column, end_row=4, end_column=column + span - 1)
        _head_cell(ws.cell(row=4, column=column, value=day_name), styles)
        for offset, number in enumerate(periods):
            _head_cell(ws.cell(row=5, column=column + offset, value=number), styles)
        column += span

    ws.row_dimensions[4].height = 22
    ws.row_dimensions[5].height = 18

    # ── السطور: خانةُ القسم ممتدّةٌ على معلّميه، كما في الورقة ──
    band = False
    layout = (first_period_col, len(periods), num_cols)
    for index, row_data in enumerate(matrix):
        if row_data.get("dept_span"):
            band = not band
        _matrix_row(ws, styles, row_data, 6 + index, band, layout)

    # ── سطرُ المجموع ──
    last_row = 6 + len(matrix)
    if totals:
        ws.merge_cells(start_row=last_row, start_column=1, end_row=last_row, end_column=2)
        ws.cell(row=last_row, column=1, value="مجموع الحصص")
        short_columns = set()
        for day_index, day in enumerate(totals.get("days") or []):
            for period_index, column_totals in enumerate(day):
                column = first_period_col + day_index * len(periods) + period_index
                ws.cell(row=last_row, column=column, value=column_totals["count"])
                if column_totals.get("short"):
                    short_columns.add(column)
        ws.cell(row=last_row, column=num_cols, value=totals.get("total") or 0)
        ExcelService._style_data_row(ws, styles, last_row, num_cols, False)
        # سطرُ المجموع عريضٌ كلُّه، وعمودٌ فيه شعبةٌ بلا درسٍ أحمر — كالورقة
        # المطبوعة: العلامةُ هناك لونٌ وخطٌّ تحته، وهنا لونٌ وعرضٌ في خانةٍ
        # لا تُقرأ إلّا على الشاشة.
        for column in range(1, num_cols + 1):
            ws.cell(row=last_row, column=column).font = xl_font(
                brand.STATUS_DANGER_FG if column in short_columns else brand.TEXT_PRIMARY, bold=True
            )

    # ── مفتاحُ الحصص المحوَّلة وملاحظاتُ الأسبوع (الأسبوعُ الفعليّ) ──
    legend_start = last_row + 2
    end_row = _legend_rows(ws, ctx, legend_start, num_cols)
    if end_row >= legend_start:  # كُتب شيءٌ — فمنطقةُ الطباعة تشمله
        last_row = end_row

    # ── القياسات والطباعة ──
    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 26
    for column in range(first_period_col, num_cols):
        ws.column_dimensions[get_column_letter(column)].width = _CELL_WIDTH
    ws.column_dimensions[get_column_letter(num_cols)].width = 8
    # التجميدُ عند C6: القسمُ والمعلّمُ يبقيان مع التمرير عرضاً، والرأسُ طولاً.
    ws.freeze_panes = "C6"

    ExcelService._apply_protection(ws, num_cols)
    ExcelService._setup_print(ws, num_cols, len(matrix) + 2, paper="a3", orientation="landscape")
    ws.print_title_rows = "1:5"
    ws.print_area = f"A1:{get_column_letter(num_cols)}{last_row}"
    return wb


def _grid_workbook(ctx: dict):
    """جدولُ معلّمٍ أو شعبة: السطرُ يومٌ والعمودُ حصّة — كالورقة سواءً بسواء.

    وكان العكسَ حتّى 2026-09-08. والمصدَّرُ يتبع المعروض: من صدّر ما رآه ثمّ
    وجده مقلوباً في الملفّ ظنّ أحدَهما خطأً.
    """
    from openpyxl.styles import Alignment

    from reports.services import ExcelService

    week = ctx.get("week") or {"columns": [], "lines": []}
    view_type = ctx.get("view_type")
    columns_spec = week["columns"]

    num_cols = 1 + len(columns_spec)
    wb, ws, styles = _sheet("الجدول", ctx.get("title") or "الجدول الدراسي", ctx, num_cols)

    # بين الحصص الفسحةُ والصلاة كالورقة (operations/schedule_paper.py) — عمودٌ ضيّق.
    columns = [("اليوم", 14)] + [
        (f"الحصة {column['number']}", 26) if column["kind"] == "period" else (column["label"], 12)
        for column in columns_spec
    ]
    ExcelService._add_header_row(ws, styles, 4, columns)

    for index, line in enumerate(week["lines"]):
        row_num = 5 + index
        # اسمُ اليوم في العمود الأوّل — والتوقيتُ في كلّ خانة، كالورقة: جرسُ
        # الخميس يخالف غيرَه، فترويسةُ عمودٍ واحدةٌ تكذب على أحدهما.
        ws.cell(row=row_num, column=1, value=line["day"])
        for position, entry in enumerate(line["entries"]):
            if entry["kind"] == "period":
                value = "\n".join(_slot_text(slot, view_type) for slot in entry["slots"]) or "—"
            else:
                value = "\n".join(
                    f"{item.label}{f' ({item.band})' if item.band else ''} "
                    f"{item.start:%H:%M} – {item.end:%H:%M}"
                    for item in entry["items"]
                )
            ws.cell(row=row_num, column=2 + position, value=value)
        ExcelService._style_data_row(ws, styles, row_num, num_cols, index % 2 == 1)
        for position, entry in enumerate(line["entries"]):
            _mark_moved(ws, row_num, 2 + position, entry.get("change", ""))
        ws.row_dimensions[row_num].height = 60

    for column in range(1, num_cols + 1):
        ws.cell(row=4, column=column).alignment = Alignment(
            horizontal="center", vertical="center", wrap_text=True
        )

    ws.freeze_panes = "B5"
    ExcelService._apply_protection(ws, num_cols)
    ExcelService._setup_print(ws, num_cols, len(week["lines"]), paper="a4", orientation="landscape")

    # مفتاحُ الحصص المحوَّلة وملاحظاتُ الأسبوع (الأسبوعُ الفعليّ) تحت الجدول وفي منطقة الطباعة.
    table_end = 4 + len(week["lines"])
    legend_start = table_end + 2
    end_row = _legend_rows(ws, ctx, legend_start, num_cols)
    if end_row >= legend_start:
        from openpyxl.utils import get_column_letter

        ws.print_area = f"A1:{get_column_letter(num_cols)}{end_row}"
    return wb


def _slot_text(slot, view_type: str | None) -> str:
    """نصُّ الخانة: المادّةُ، ثمّ من لا يُعرف من العنوان، ثمّ توقيتُ الحصّة.

    والتوقيتُ في الخانة لا في عمود الحصص: خانتان في العمود الواحد قد تختلف
    ساعتاهما (طابقان بجرسين)، فتوقيتُ العمود يكذب على إحداهما.
    """
    parts = [slot.subject.name_ar if slot.subject else "—"]
    if view_type != "teacher" and slot.teacher_id:
        parts.append(slot.teacher.full_name)
    if view_type != "class":
        parts.append(slot.class_group.short_label)
    if slot.start_time and slot.end_time:
        parts.append(f"{slot.start_time:%H:%M} – {slot.end_time:%H:%M}")
    text = " — ".join(part for part in parts if part)
    # حصّةٌ حُوّل معلّمُها (أسبوعٌ فعليّ): «عن فلان» في سطرٍ خاصّ — وحصصُ الخطّة بلا `note`.
    note = getattr(slot, "note", "")
    return f"{text}\n{note}" if note else text


def _head_cell(cell, styles: dict):
    """خانةُ رأسٍ بأنماط المنصّة — كستنائيّةٌ بيضاءُ الخطّ موسَّطة."""
    cell.font = styles["header_font"]
    cell.fill = styles["header_fill"]
    cell.alignment = styles["header_align"]
    cell.border = styles["thin_border"]
    return cell
