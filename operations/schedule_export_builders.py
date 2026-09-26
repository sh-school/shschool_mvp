"""بنّاءاتُ تصدير الجدول (PDF/Excel) لسجلّ التصدير المركزيّ (`core.exports.registry`).

دوالُّ نقيّةٌ بلا `request`: تعمل في عاملِ Celery (`core.export.run_job`) بما كانت تفعله `render_schedule_export_task`
حرفاً — السياقُ من `query_string` المحفوظة، والقالبُ `for_pdf` بلا سكربتٍ ولا `{% static %}` غيرِ محروس
(Sentry SCHOOLOS-PRODUCTION-2X، `tests/test_schedule_pdf_static.py`). وتُسجَّل من `OperationsConfig.ready()`.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

from django.template.loader import render_to_string

from core.exports.registry import ExportResult

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _paper(ctx: dict[str, Any]) -> str:
    return "A3" if ctx.get("paper") == "a3" else "A4"


def build_schedule_pdf(school: Any, user: Any, params: Any) -> ExportResult:
    from core.pdf_utils import render_pdf_bytes
    from operations.schedule_selectors import export_filename, schedule_print_payload

    ctx = schedule_print_payload(school, user, params)
    ctx["embed"] = True
    ctx["for_pdf"] = True
    html = render_to_string("schedule/print_schedule.html", ctx)
    return ExportResult(
        render_pdf_bytes(html, paper_size=_paper(ctx)),
        "application/pdf",
        export_filename(ctx, "pdf"),
    )


def build_schedule_xlsx(school: Any, user: Any, params: Any) -> ExportResult:
    from operations.schedule_export import schedule_workbook
    from operations.schedule_selectors import export_filename, schedule_print_payload

    ctx = schedule_print_payload(school, user, params)
    ctx["embed"] = True
    buffer = BytesIO()
    schedule_workbook(ctx).save(buffer)
    return ExportResult(buffer.getvalue(), XLSX_TYPE, export_filename(ctx, "xlsx"))


def build_schedule_pages_pdf(school: Any, user: Any, params: Any) -> ExportResult:
    """صفحةٌ لكلّ معلّمٍ أو شعبة — الأثقلُ في المنصّة (19.9ث متزامناً على قاعدة القياس 2026-09-26)."""
    from core.pdf_utils import render_pdf_bytes
    from operations.schedule_selectors import export_filename, pages_payload

    ctx = pages_payload(school, params)
    ctx["embed"] = True
    ctx["for_pdf"] = True
    html = render_to_string("schedule/print_pages.html", ctx)
    return ExportResult(
        render_pdf_bytes(html, paper_size=_paper(ctx)),
        "application/pdf",
        export_filename(ctx, "pdf"),
    )
