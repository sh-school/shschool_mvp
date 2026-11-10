"""بنّاءُ قائمة الطلاب PDF لسجلّ التصدير المركزيّ (`core.exports.registry`).

دالّةٌ نقيّةٌ بلا `request`: تعمل في عاملِ Celery (`core.export.run_job`) — السياقُ من المستخدم ومن `query_string`
المحفوظة، والقالبُ `for_pdf` فلا شريطَ رجوعٍ ولا `{% static %}` (العاملُ لا يملك manifest الويب: Sentry SCHOOLOS-PRODUCTION-2X).
وتُسجَّل من `StudentAffairsConfig.ready()`.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from django.template.loader import render_to_string

from core.academic_calendar import academic_year_for_school
from core.export_utils import (
    apply_print_footer,
    generate_export_filename,
    get_export_context_for,
    get_pdf_footer_html,
    get_pdf_header_html,
)
from core.exports.contract import NUMBER_LABEL, Column, TableSpec, table_rows
from core.exports.registry import ExportResult

from .list_selectors import rows_for

#: قائمةُ الطلبة على عقد التصدير المركزيّ (W-20261109-013): الصفوفُ من محدِّد الشاشة نفسِه `rows_for`.
STUDENT_LIST_TABLE = TableSpec(
    kind="student_affairs.student_list_xlsx",
    title="سجل الطلاب",
    capability="student_affairs.view",
    columns=(
        Column("full_name", "الاسم الكامل"),
        Column("national_id", "الرقم الشخصي"),
        Column("class_label", "الصف والشعبة"),
        Column("guardian_name", "ولي الأمر"),
        Column("guardian_relation", "الصلة"),
        Column("guardian_phone", "جوال ولي الأمر"),
    ),
    rows_for=rows_for,
    file_module="students",
)

#: أعمدةُ PDF: كشفٌ جماعيٌّ فلا رقمَ شخصيَّ فيه ولو مستوراً (`core/privacy.py`)؛ والصفوفُ من `rows_for` نفسِه.
STUDENT_LIST_PDF_TABLE = replace(
    STUDENT_LIST_TABLE,
    kind="student_affairs.students_pdf",
    columns=tuple(c for c in STUDENT_LIST_TABLE.columns if c.key != "national_id"),
)


def build_students_pdf(school: Any, user: Any, params: Any) -> ExportResult:
    """كان متزامناً 8.3ث على قاعدة القياس (2026-09-26): WeasyPrint على سجلّ المدرسة كلِّه.

    الرقمُ الشخصيُّ يصل القالبَ خاماً ويستره `|mask_id` هناك — كشفٌ جماعيّ (`core/privacy.py`)، فالرايةُ كاذبة.
    """
    from core.pdf_utils import render_pdf_bytes

    ctx = get_export_context_for(user, "سجل الطلاب")
    # المحدِّدُ نفسُه الذي تقرأ به الشاشةُ وExcel: نطاقُ الدور والفلترُ كاملاً والعمودُ «م» وفرزُ الجناح والأعمدةُ المخفيّة.
    columns, rows = table_rows(STUDENT_LIST_PDF_TABLE, user, params)

    html = render_to_string(
        "student_affairs/student_list_pdf.html",
        {
            "headers": [NUMBER_LABEL, *(c.label for c in columns)],
            "rows": rows,
            "total_students": len(rows),
            "pdf_header": get_pdf_header_html(ctx),
            "pdf_footer": get_pdf_footer_html(ctx),
            "for_pdf": True,
            **ctx,
        },
    )
    return ExportResult(
        render_pdf_bytes(html, paper_size="A4"),
        "application/pdf",
        generate_export_filename("students", "list", "pdf"),
        rows=len(rows),
        full_national_id=False,
    )


def build_movements_xlsx(school: Any, user: Any, params: Any) -> ExportResult:
    """تحرّكات الطلبة Excel بمرشِّحات الشاشة نفسِها. الرقمُ الشخصيّ لا يدخل الملفّ: قائمةٌ جماعيّة بالأسماء."""
    from io import BytesIO

    import openpyxl
    from openpyxl.styles import Alignment

    from core.excel_safety import safe_cell
    from core.export_utils import add_excel_footer, add_excel_header, excel_table_styles

    from .selectors import enrolment_movements, movement_filters

    year = academic_year_for_school(school)
    events = enrolment_movements(school, year, **movement_filters(params))
    ctx = get_export_context_for(user, "تحرّكات الطلبة")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "تحرّكات الطلبة"
    ws.sheet_view.rightToLeft = True

    headers = ["#", "التاريخ", "الطالب", "الحركة", "الشعبة", "من شعبة", "تفاصيل"]
    data_start = add_excel_header(ws, ctx, len(headers))
    table = excel_table_styles()
    for col, h in enumerate(headers, 1):
        cell = safe_cell(ws, row=data_start, column=col, value=h)
        cell.fill = table.header_fill
        cell.font = table.header_font
        cell.alignment = Alignment(horizontal="center")
        cell.border = table.border

    for i, e in enumerate(events, 1):
        row = [
            i,
            e["date"].isoformat(),
            e["student"].full_name,
            e["kind_label"],
            e["class_text"],
            e["from_text"],
            e["detail"],
        ]
        for col, val in enumerate(row, 1):
            cell = safe_cell(ws, row=data_start + i, column=col, value=val)
            cell.font = table.cell_font
            cell.border = table.border
            if i % 2 == 0:
                cell.fill = table.alt_fill

    for col_idx in range(1, len(headers) + 1):
        longest = max(
            len(str(ws.cell(row=r, column=col_idx).value or ""))
            for r in range(data_start, data_start + len(events) + 1)
        )
        ws.column_dimensions[chr(64 + col_idx)].width = min(longest + 4, 40)

    add_excel_footer(ws, ctx, data_start + len(events), len(headers))
    # رؤية الوزارة في ذيل الطباعة قبل الحفظ (قاعدة كل مصنّف مصدَّر)
    apply_print_footer(wb, school)
    buffer = BytesIO()
    wb.save(buffer)
    return ExportResult(
        buffer.getvalue(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        generate_export_filename("student", "movements", "xlsx"),
        rows=len(events),
        full_national_id=False,
    )
