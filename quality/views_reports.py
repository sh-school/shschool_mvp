"""
quality/views_reports.py — تقرير التقدم + PDF
"""
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils import timezone

from core.pdf_utils import render_pdf

from .models import OperationalProcedure
from .services import QualityService


@login_required
def progress_report(request):
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    year   = request.GET.get("year", "2025-2026")
    data   = QualityService.get_progress_report_data(school, year)

    executor_stats = (
        OperationalProcedure.objects.filter(school=school, academic_year=year)
        .values("executor_norm")
        .annotate(total=Count("id"), completed=Count("id", filter=Q(status="Completed")))
        .order_by("-total")[:20]
    )

    return render(request, "quality/progress_report.html", {
        "domain_stats":   data["domain_stats"],
        "executor_stats": executor_stats,
        "year":           year,
    })


@login_required
def progress_report_pdf(request):
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school   = request.user.get_school()
    year     = request.GET.get("year", "2025-2026")
    data     = QualityService.get_progress_report_data(school, year)
    overall  = data["overall"]

    html_content = render_to_string("quality/pdf/progress_report.html", {
        "domain_stats":  data["domain_stats"],
        "year":          year,
        "school":        school,
        "total_all":     overall["total"],
        "completed_all": overall["completed"],
        "pct_all":       overall["pct"],
        "generated_at":  timezone.now(),
    }, request=request)

    return render_pdf(html_content, f"operational_plan_{year}.pdf")
