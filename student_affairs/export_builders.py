"""بنّاءُ قوائم الطلاب PDF لسجلّ التصدير المركزيّ (`core.exports.registry`).

دالّةٌ نقيّةٌ بلا `request`: تعمل في عاملِ Celery (`core.export.run_job`) — السياقُ من المستخدم ومن `query_string`
المحفوظة، والقالبُ `for_pdf` فلا شريطَ رجوعٍ ولا `{% static %}` (العاملُ لا يملك manifest الويب: Sentry SCHOOLOS-PRODUCTION-2X).
وتُسجَّل من `StudentAffairsConfig.ready()`.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from django.template.loader import render_to_string

from core.export_utils import (
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
    return build_table_pdf(
        STUDENT_LIST_PDF_TABLE,
        ("إجمالي الطلاب المقيَّدين", "قائمة الطلاب", ""),
        school,
        user,
        params,
    )


def build_table_pdf(
    spec: TableSpec,
    labels: tuple[str, str, str],
    school: Any,
    user: Any,
    params: Any,
) -> ExportResult:
    """PDF لجدولٍ على العقد المركزيّ: الصفوفُ من محدِّد الجدول نفسِه الذي تقرأ به الشاشةُ وExcel (`table_rows`).

    `labels` = (عنوانُ مؤشّر العدد، عنوانُ القسم، عبارةُ الفراغ — فارغةٌ تعني عبارةَ القالب)؛
    والقالبُ `student_list_pdf.html` واحدٌ للجداول كلِّها.
    """
    from core.pdf_utils import render_pdf_bytes

    ctx = get_export_context_for(user, spec.title)
    # المحدِّدُ نفسُه الذي تقرأ به الشاشةُ وExcel: نطاقُ الدور والفلترُ كاملاً والعمودُ «م» وفرزُ الجناح والأعمدةُ المخفيّة.
    columns, rows = table_rows(spec, user, params)
    kpi_label, section_title, empty_label = labels
    html = render_to_string(
        "student_affairs/student_list_pdf.html",
        {
            "headers": [NUMBER_LABEL, *(c.label for c in columns)],
            "rows": rows,
            "total_students": len(rows),
            "kpi_label": kpi_label,
            "section_title": section_title,
            "empty_label": empty_label,
            "pdf_header": get_pdf_header_html(ctx),
            "pdf_footer": get_pdf_footer_html(ctx),
            "for_pdf": True,
            **ctx,
        },
    )
    return ExportResult(
        render_pdf_bytes(html, paper_size="A4"),
        "application/pdf",
        generate_export_filename(spec.file_module, "list", "pdf"),
        rows=len(rows),
        full_national_id=False,
    )
