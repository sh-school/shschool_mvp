"""بنّاءُ قائمة الطلاب PDF لسجلّ التصدير المركزيّ (`core.exports.registry`).

دالّةٌ نقيّةٌ بلا `request`: تعمل في عاملِ Celery (`core.export.run_job`) — السياقُ من المستخدم ومن `query_string`
المحفوظة، والقالبُ `for_pdf` فلا شريطَ رجوعٍ ولا `{% static %}` (العاملُ لا يملك manifest الويب: Sentry SCHOOLOS-PRODUCTION-2X).
وتُسجَّل من `StudentAffairsConfig.ready()`.
"""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string

from core.academic_calendar import academic_year_for_school
from core.export_utils import (
    generate_export_filename,
    get_export_context_for,
    get_pdf_footer_html,
    get_pdf_header_html,
)
from core.exports.registry import ExportResult

from .selectors import student_register


def build_students_pdf(school: Any, user: Any, params: Any) -> ExportResult:
    """كان متزامناً 8.3ث على قاعدة القياس (2026-09-26): WeasyPrint على سجلّ المدرسة كلِّه.

    الرقمُ الشخصيُّ يصل القالبَ خاماً ويستره `|mask_id` هناك — كشفٌ جماعيّ (`core/privacy.py`)، فالرايةُ كاذبة.
    """
    from core.pdf_utils import render_pdf_bytes

    year = academic_year_for_school(user.get_school())
    ctx = get_export_context_for(user, "سجل الطلاب")
    students, enrollment_data = student_register(school, year, params)

    rows = []
    for i, m in enumerate(students, 1):
        enr = enrollment_data.get(m.user_id, {})
        rows.append(
            {
                "num": i,
                "full_name": m.user.full_name,
                "national_id": m.user.national_id,
                "grade": enr.get("class_group__grade", "—"),
                "section": enr.get("class_group__section", "—"),
                "phone": m.user.phone or "—",
                "email": m.user.email or "—",
            }
        )

    html = render_to_string(
        "student_affairs/student_list_pdf.html",
        {
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
