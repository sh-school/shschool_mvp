"""
quality/views_committee.py — لجنة المراجعة الذاتية + لجنة المنفذين
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.models import CustomUser, Membership

from .models import (
    OperationalDomain,
    OperationalProcedure,
    QualityCommitteeMember,
)
from .services import QualityService

_DEFAULT_YEAR = settings.CURRENT_ACADEMIC_YEAR


def _committee_redirect(committee_type, year):
    """Clean Code: لا URLs مشفرة — استخدام reverse()"""
    url_name = (
        "executor_committee"
        if committee_type == QualityCommitteeMember.EXECUTOR
        else "quality_committee"
    )
    return f"{reverse(url_name)}?year={year}"


@login_required
def quality_committee(request):
    school = request.user.get_school()
    year = request.GET.get("year", _DEFAULT_YEAR)

    staff_ids = Membership.objects.filter(school=school, is_active=True).values_list(
        "user_id", flat=True
    )

    members = QualityCommitteeMember.objects.review_committee(school, year)

    # ── Bulk counts بدلاً من N+1 ────────────────────────────
    from django.db.models import Count

    # عدد المراجعات لكل مستخدم
    reviewed_map = dict(
        OperationalProcedure.objects.filter(
            school=school, academic_year=year, reviewed_by__isnull=False
        )
        .values_list("reviewed_by")
        .annotate(c=Count("id"))
        .values_list("reviewed_by", "c")
    )
    # عدد الإجراءات المعلقة لكل مجال
    pending_map = dict(
        OperationalProcedure.objects.filter(
            school=school, academic_year=year, status="Pending Review"
        )
        .values("indicator__target__domain")
        .annotate(c=Count("id"))
        .values_list("indicator__target__domain", "c")
    )

    member_review_stats = []
    for member in members:
        member_review_stats.append(
            {
                "member": member,
                "reviewed_count": reviewed_map.get(member.user_id, 0) if member.user_id else 0,
                "pending_in_domain": pending_map.get(member.domain_id, 0)
                if member.domain_id
                else 0,
            }
        )

    return render(
        request,
        "quality/committee.html",
        {
            "members": members,
            "member_review_stats": member_review_stats,
            "year": year,
            "committee_type": QualityCommitteeMember.REVIEW,
            "committee_label": "لجنة المراجعة الذاتية",
            "staff": CustomUser.objects.filter(id__in=staff_ids).order_by("full_name"),
            "domains": OperationalDomain.objects.filter(school=school, academic_year=year).order_by(
                "order"
            ),
            "RESP_CHOICES": QualityCommitteeMember.RESPONSIBILITY,
        },
    )


@login_required
@require_POST
def add_committee_member(request):
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    year = request.POST.get("year", _DEFAULT_YEAR)
    user_id = request.POST.get("user_id", "").strip()
    job_title = request.POST.get("job_title", "").strip()
    responsibility = request.POST.get("responsibility", "عضو")
    committee_type = request.POST.get("committee_type", QualityCommitteeMember.REVIEW)
    domain_id = request.POST.get("domain_id", "").strip() or None

    user = CustomUser.objects.filter(id=user_id).first() if user_id else None
    domain = (
        OperationalDomain.objects.filter(id=domain_id, school=school).first() if domain_id else None
    )

    if not job_title and not user:
        messages.error(request, "يجب تحديد المستخدم أو المسمى الوظيفي")
        return redirect(_committee_redirect(committee_type, year))

    if not job_title and user:
        job_title = getattr(user, "job_title", "") or str(user)

    QualityCommitteeMember.objects.get_or_create(
        school=school,
        academic_year=year,
        user=user,
        committee_type=committee_type,
        defaults={
            "job_title": job_title,
            "responsibility": responsibility,
            "domain": domain,
            "is_active": True,
        },
    )

    messages.success(request, f"✅ تم إضافة {job_title} للجنة")
    return redirect(_committee_redirect(committee_type, year))


@login_required
@require_POST
def remove_committee_member(request, member_id):
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    member = get_object_or_404(QualityCommitteeMember, id=member_id, school=school)
    committee_type, year = member.committee_type, member.academic_year
    member.delete()

    messages.success(request, "تم إزالة العضو من اللجنة")
    return redirect(_committee_redirect(committee_type, year))


@login_required
def executor_committee(request):
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    year = request.GET.get("year", _DEFAULT_YEAR)

    data = QualityService.get_executor_committee_data(school, year)
    staff_ids = Membership.objects.filter(school=school, is_active=True).values_list(
        "user_id", flat=True
    )

    return render(
        request,
        "quality/executor_committee.html",
        {
            "member_stats": data["member_stats"],
            "unmapped_norms": data["unmapped_norms"],
            "year": year,
            "total_all": data["overall"]["total"],
            "completed_all": data["overall"]["completed"],
            "pct_all": data["overall"]["pct"],
            "committee_type": QualityCommitteeMember.EXECUTOR,
            "committee_label": "لجنة منفذي الخطة التشغيلية",
            "all_users": CustomUser.objects.filter(id__in=staff_ids).order_by("full_name"),
            "domains": OperationalDomain.objects.filter(school=school, academic_year=year).order_by(
                "order"
            ),
        },
    )


@login_required
def executor_member_detail(request, member_id):
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    member = get_object_or_404(
        QualityCommitteeMember,
        id=member_id,
        school=school,
        committee_type=QualityCommitteeMember.EXECUTOR,
    )

    year = request.GET.get("year", _DEFAULT_YEAR)
    status_filter = request.GET.get("status", "")
    domain_filter = request.GET.get("domain", "")

    data = QualityService.get_executor_detail(member, school, year)
    qs = data["procedures"]

    if status_filter:
        qs = qs.filter(status=status_filter)
    if domain_filter:
        qs = qs.filter(indicator__target__domain__id=domain_filter)

    stats = QualityService._calc_stats(qs)

    return render(
        request,
        "quality/executor_member_detail.html",
        {
            "member": member,
            "procedures": qs,
            "year": year,
            "status_filter": status_filter,
            "domain_filter": domain_filter,
            "domains": OperationalDomain.objects.filter(school=school, academic_year=year),
            "STATUS_CHOICES": OperationalProcedure.STATUS,
            **stats,
        },
    )
