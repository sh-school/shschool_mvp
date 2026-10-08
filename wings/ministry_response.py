"""استجابةُ ملخّص الحصّتين الأولى والثانية — شاشةَ منصّةٍ أو PDF أو Excel. (كتابتُها هنا لا في العرض: طبقاتُ المنصّة.)"""

from django.shortcuts import render
from django.template.loader import render_to_string

from core.audit_export import log_export
from core.export_utils import generate_export_filename, get_export_context
from core.pdf_utils import render_pdf
from reports.services import ExcelService

from .ministry_excel import ministry_workbook
from .ministry_selectors import MinistrySummary
from .register import footer_lines

TITLE = "ملخّصُ غياب الحصّتين الأولى والثانية"


def respond(
    request,
    school,
    summary: MinistrySummary,
    *,
    fmt: str,
    orient: str,
    bound: bool,
    screen: dict | None = None,
):
    """يُخرج الملخّصَ بالصيغة المطلوبة؛ والتصديرُ مدقَّق بلا رقمٍ شخصيّ."""
    ctx = get_export_context(request, TITLE)
    ctx.update(
        school=school, summary=summary, orient=orient, footer=footer_lines(school), bound=bound
    )
    if fmt == "xlsx":
        log_export(request, "wings.ministry_xlsx", object_repr=TITLE)
        return ExcelService.to_response(
            ministry_workbook(summary, ctx["school_name"], ctx["exported_by"], orient),
            generate_export_filename("wings", "ministry_p1p2", "xlsx"),
            school=school,
        )
    if fmt == "pdf":
        log_export(request, "wings.ministry_pdf", object_repr=TITLE)
        html = render_to_string("wings/ministry_pdf.html", ctx, request=request)
        return render_pdf(
            html, generate_export_filename("wings", "ministry_p1p2", "pdf"), as_attachment=True
        )
    ctx.update(screen or {})
    ctx.update(day=summary.day, bound=bound, filtered=bool(ctx.get("grade") or ctx.get("q")))
    ctx["subtitle"] = f"للرفع في نظام الوزارة · {summary.day:%d/%m/%Y} · " + (
        "طلبةُ جناحك" if bound else "المدرسةُ كلُّها"
    )
    return render(request, "wings/ministry_report.html", ctx)
