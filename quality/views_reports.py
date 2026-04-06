"""
quality/views_reports.py — تقرير التقدم + PDF
"""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils import timezone

from core.pdf_utils import render_pdf
from core.permissions import QUALITY_MANAGE, QUALITY_VIEW, role_required

# All roles that can access quality module
_QUALITY_ALL = QUALITY_MANAGE | QUALITY_VIEW | {"ese_teacher"}

from .models import ExecutorMapping, OperationalProcedure, QualityCommitteeMember
from .services import QualityService

_DEFAULT_YEAR = settings.CURRENT_ACADEMIC_YEAR


@login_required
@role_required(_QUALITY_ALL)
def progress_report(request):
    school = request.user.get_school()
    year = request.GET.get("year", _DEFAULT_YEAR)
    data = QualityService.get_progress_report_data(school, year)
    overall = data["overall"]

    # ── المنفذين مع اسم الموظف الفعلي ──
    executor_raw = (
        OperationalProcedure.objects.filter(school=school, academic_year=year)
        .values("executor_norm")
        .annotate(total=Count("id"), completed=Count("id", filter=Q(status="Completed")))
        .order_by("-total")[:20]
    )
    # بناء خريطة اسم المنفذ → اسم الموظف
    mapping_dict = dict(
        ExecutorMapping.objects.filter(
            school=school, academic_year=year, user__isnull=False,
        ).select_related("user").values_list("executor_norm", "user__full_name")
    )
    executor_stats = []
    for ex in executor_raw:
        ex["user_name"] = mapping_dict.get(ex["executor_norm"], "")
        executor_stats.append(ex)

    # ── مسؤول كل مجال (من لجنة المراجعة) ──
    reviewer_map = {}
    for m in QualityCommitteeMember.objects.filter(
        school=school, committee_type=QualityCommitteeMember.REVIEW,
        is_active=True, domain__isnull=False,
    ).select_related("user", "domain"):
        if m.domain_id and m.user:
            reviewer_map[m.domain_id] = m.user.full_name

    domain_stats = data["domain_stats"]
    for ds in domain_stats:
        ds["reviewer_name"] = reviewer_map.get(ds["domain"].pk, "")

    base_qs = OperationalProcedure.objects.filter(school=school, academic_year=year)
    today = timezone.now().date()
    overdue_qs = base_qs.overdue().with_details()

    overdue_procedures = [
        {"procedure": proc, "days_overdue": (today - proc.deadline).days if proc.deadline else 0}
        for proc in overdue_qs[:30]
    ]

    evidence_requests = base_qs.filter(evidence_request_status="requested").with_details()[:10]

    return render(
        request,
        "quality/progress_report.html",
        {
            "domain_stats": domain_stats,
            "executor_stats": executor_stats,
            "year": year,
            "total_all": overall["total"],
            "completed_all": overall["completed"],
            "in_progress_all": overall["in_progress"],
            "pending_review_all": overall["pending_review"],
            "pct_all": overall["pct"],
            "overdue_procedures": overdue_procedures,
            "overdue_count": len(overdue_procedures),
            "evidence_requests": evidence_requests,
        },
    )


@login_required
@role_required(_QUALITY_ALL)
def progress_report_pdf(request):
    school = request.user.get_school()
    year = request.GET.get("year", _DEFAULT_YEAR)
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
