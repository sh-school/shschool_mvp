"""بنّاءُ تصدير الجودة: طباعةُ «نموذج 19» (متابعة أداء المشرف الإداريّ) — بلا `request`، يعمل في العامل."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string

from core.exports.registry import ExportResult

from . import supervisor_followup_selectors as selectors

TEMPLATE = "quality/supervisor_followup_pdf.html"


def build_supervisor_followup_pdf(school: Any, user: Any, params: Any) -> ExportResult:
    """المتابعةُ بترتيب الورقة؛ وإذنُ الصفّ يُفحص هنا أيضاً لأنّ العاملَ يعيد فحصَ القدرة وحدَها."""
    from core.pdf_utils import render_pdf_bytes

    followup = selectors.readable_follow_up(school, user, params.get("followup", ""))
    html = render_to_string(TEMPLATE, selectors.print_context(school, followup))
    return ExportResult(
        render_pdf_bytes(html),
        "application/pdf",
        f"نموذج_19_{followup.follow_date:%Y-%m-%d}.pdf",  # بلا اسم: اسمُ الملفّ يُشارَك ويُسجَّل
        rows=1,
        object_id=str(followup.pk),
    )
