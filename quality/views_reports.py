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
    year = request.GET.get("year", "2025-2026")
    data = QualityService.get_progress_report_data(school, year)

    executor_stats = (
        OperationalProcedure.objects.filter(school=school, academic_year=year)
        .values("executor_norm")
        .annotate(total=Count("id"), completed=Count("id", filter=Q(status="Completed")))
        .order_by("-total")[:20]
    )

    base_qs = OperationalProcedure.objects.filter(school=school, academic_year=year)
    overall = data.get("overall", {})
    total_all = overall.get("total", base_qs.count())
    completed_all = overall.get("completed", base_qs.filter(status="Completed").count())
    in_progress_all = base_qs.filter(status="In Progress").count()
    pending_review_all = base_qs.filter(status="Pending Review").count()
    pct_all = round(completed_all / total_all * 100) if total_all else 0

    today = timezone.now().date()
    overdue_qs = base_qs.overdue().with_details()
    overdue_count = overdue_qs.count()
    overdue_procedures = []
    for proc in overdue_qs[:30]:
        days_overdue = (today - proc.deadline).days if proc.deadline else 0
        overdue_procedures.append({
            "procedure": proc,
            "days_overdue": days_overdue,
        })

    evidence_requests = base_qs.filter(
        evidence_request_status="requested"
    ).with_details()[:10]

    return render(
        request,
        "quality/progress_report.html",
        {
            "domain_stats": data["domain_stats"],
            "executor_stats": executor_stats,
            "year": year,
            "total_all": total_all,
            "completed_all": completed_all,
            "in_progress_all": in_progress_all,
            "pending_review_all": pending_review_all,
            "pct_all": pct_all,
            "overdue_procedures": overdue_procedures,
            "overdue_count": overdue_count,
            "evidence_requests": evidence_requests,
        },
    )


@login_required
def progress_report_pdf(request):
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    year = request.GET.get("year", "2025-2026")
    data = QualityService.get_progress_report_data(school, year)
    overall = data["overall"]

    html_content = render_to_string(
        "quality/pdf/progress_report.html",
        {
            "domain_stats": data["domain_stats"],
            "year": year,
            "school": school,
            "total_all": overall["total"],
            "completed_all": overall["completed"],
            "pct_all": overall["pct"],
            "generated_at": timezone.now(),
        },
        request=request,
    )

    return render_pdf(html_content, f"operational_plan_{year}.pdf")
