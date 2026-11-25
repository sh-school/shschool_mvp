"""بنّاءُ «نموذج 19» PDF في سجلّ التصدير المركزيّ — بلا `request`: يعمل في العامل (التنزيل) وفي المعاينة المضمَّنة."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string

from core.exports.registry import ExportResult

from . import supervisor_followup_selectors as selectors

KIND = "quality.supervisor_followup_pdf"


def build_followup_pdf(school: Any, user: Any, params: Any) -> ExportResult:
    """القراءةُ بقاعدة الشاشة نفسِها (`readable_follow_up`) فتُفحص ثانيةً في العامل."""
    from core.pdf_utils import render_pdf_bytes

    followup = selectors.readable_follow_up(school, user, params["pk"])
    html = render_to_string(
        "quality/supervisor_followup_pdf.html", selectors.print_context(school, followup)
    )
    return ExportResult(
        render_pdf_bytes(html),
        "application/pdf",
        # اسمُ الملفّ بلا اسمِ شخص: يُشارَك ويُسجَّل
        f"نموذج_19_{followup.follow_date:%Y-%m-%d}.pdf",
        rows=1,
        object_id=str(followup.pk),
    )
