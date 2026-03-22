"""
quality/views_committee.py — لجنة المراجعة الذاتية + لجنة المنفذين
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.models import CustomUser, Membership

from .models import (
    OperationalDomain,
    OperationalProcedure,
    QualityCommitteeMember,
)
from .services import QualityService


@login_required
def quality_committee(request):
    school = request.user.get_school()
    year = request.GET.get("year", "2025-2026")

    staff_ids = Membership.objects.filter(school=school, is_active=True).values_list(
        "user_id", flat=True
    )

    return render(
        request,
        "quality/committee.html",
        {
            "members": QualityCommitteeMember.objects.review_committee(school, year),
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


def _committee_redirect(committee_type, year):
    if committee_type == QualityCommitteeMember.EXECUTOR:
        return f"/quality/executor-committee/?year={year}"
    return f"/quality/committee/?year={year}"


@login_required
@require_POST
def add_committee_member(request):
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    year = request.POST.get("year", "2025-2026")
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
    year = request.GET.get("year", "2025-2026")

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

    year = request.GET.get("year", "2025-2026")
    status_filter = request.GET.get("status", "")
    domain_filter = request.GET.get("domain", "")

    data = QualityService.get_executor_detail(member, school, year)
    qs = data["procedures"]

    if status_filter:
        qs = qs.filter(status=status_filter)
    if domain_filter:
        qs = qs.filter(indicator__target__domain__id=domain_filter)

    total = qs.count()
    completed = qs.filter(status="Completed").count()
    pending = qs.filter(status="Pending Review").count()
    in_prog = qs.filter(status="In Progress").count()
    pct = round(completed / total * 100) if total else 0

    return render(
        request,
        "quality/executor_member_detail.html",
        {
            "member": member,
            "procedures": qs,
            "total": total,
            "completed": completed,
            "pending": pending,
            "in_prog": in_prog,
            "pct": pct,
            "year": year,
            "status_filter": status_filter,
            "domain_filter": domain_filter,
            "domains": OperationalDomain.objects.filter(school=school, academic_year=year),
            "STATUS_CHOICES": OperationalProcedure.STATUS,
        },
    )
