"""
quality/views.py — Core views: لوحة التحكم + المجال + الإجراء
المنطق الثانوي في: views_committee / views_executor / views_reports
"""
from datetime import date as _date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    OperationalDomain,
    OperationalProcedure,
    ProcedureEvidence,
    QualityCommitteeMember,
)
from .services import QualityService

# Re-exports for backward compat with urls.py
from .views_committee import (  # noqa: F401
    quality_committee, add_committee_member, remove_committee_member,
    executor_committee, executor_member_detail,
)
from .views_executor import (  # noqa: F401
    executor_mapping, save_executor_mapping, apply_all_mappings,
)
from .views_reports import progress_report, progress_report_pdf  # noqa: F401


# ── لوحة تحكم الخطة التشغيلية ──────────────────────────────

@login_required
def plan_dashboard(request):
    school = request.user.get_school()
    year   = request.GET.get("year", "2025-2026")

    domains         = OperationalDomain.objects.filter(school=school, academic_year=year).order_by("order")
    stats           = QualityService.get_plan_stats(school, year)
    review_committee = QualityCommitteeMember.objects.review_committee(school, year)

    my_procedures  = [] if request.user.is_admin() else QualityService.get_my_procedures(request.user, school, year)
    unmapped_count = QualityService.get_unmapped_count(school, year) if request.user.is_admin() else 0

    return render(request, "quality/dashboard.html", {
        "domains":          domains,
        "year":             year,
        "review_committee": review_committee,
        "my_procedures":    my_procedures,
        "unmapped_count":   unmapped_count,
        **stats,
    })


# ── تفاصيل المجال ───────────────────────────────────────────

@login_required
def domain_detail(request, domain_id):
    school          = request.user.get_school()
    domain          = get_object_or_404(OperationalDomain, id=domain_id, school=school)
    status_filter   = request.GET.get("status", "")
    executor_filter = request.GET.get("executor", "")

    data = QualityService.get_domain_procedures(school, domain, status_filter, executor_filter)

    return render(request, "quality/domain_detail.html", {
        "domain":          domain,
        "targets":         data["targets"],
        "executors":       data["executors"],
        "status_filter":   status_filter,
        "executor_filter": executor_filter,
        "STATUS_CHOICES":  OperationalProcedure.STATUS,
    })


# ── تفاصيل الإجراء ──────────────────────────────────────────

@login_required
def procedure_detail(request, proc_id):
    school    = request.user.get_school()
    procedure = get_object_or_404(OperationalProcedure, id=proc_id, school=school)
    evidences = procedure.evidences.select_related("uploaded_by").all()
    can_edit  = request.user.is_admin() or procedure.executor_user == request.user

    is_reviewer = QualityCommitteeMember.objects.filter(
        school=school, user=request.user,
        committee_type=QualityCommitteeMember.REVIEW, is_active=True,
    ).exists()

    return render(request, "quality/procedure_detail.html", {
        "procedure":      procedure,
        "evidences":      evidences,
        "can_edit":       can_edit,
        "is_reviewer":    is_reviewer,
        "STATUS_CHOICES": OperationalProcedure.STATUS,
    })


@login_required
@require_POST
def update_procedure_status(request, proc_id):
    school    = request.user.get_school()
    procedure = get_object_or_404(OperationalProcedure, id=proc_id, school=school)

    if not (request.user.is_admin() or procedure.executor_user == request.user):
        return HttpResponse("غير مسموح", status=403)

    new_status = request.POST.get("status")
    if new_status in dict(OperationalProcedure.STATUS):
        procedure.status = new_status

    eval_text = request.POST.get("evaluation", "")
    if eval_text:
        procedure.evaluation = eval_text

    deadline_str = request.POST.get("deadline", "").strip()
    if deadline_str:
        try:
            procedure.deadline = _date.fromisoformat(deadline_str)
        except ValueError:
            pass

    if new_status == "Pending Review":
        procedure.reviewed_at = None
        procedure.reviewed_by = None

    procedure.save(update_fields=["status", "evaluation", "deadline", "reviewed_at", "reviewed_by", "updated_at"])
    return render(request, "quality/partials/procedure_status_badge.html", {"procedure": procedure})


@login_required
@require_POST
def approve_procedure(request, proc_id):
    school    = request.user.get_school()
    procedure = get_object_or_404(OperationalProcedure, id=proc_id, school=school)

    is_reviewer = QualityCommitteeMember.objects.filter(
        school=school, user=request.user,
        committee_type=QualityCommitteeMember.REVIEW,
        is_active=True, can_review=True,
    ).exists()

    if not (request.user.is_admin() or is_reviewer):
        return HttpResponse("غير مسموح", status=403)

    action = request.POST.get("action")
    note   = request.POST.get("review_note", "").strip()

    if action == "approve":
        procedure.status      = "Completed"
        procedure.reviewed_by = request.user
        procedure.reviewed_at = timezone.now()
        procedure.review_note = note
        messages.success(request, f"✅ تم اعتماد الإجراء [{procedure.number}]")
    elif action == "reject":
        procedure.status      = "In Progress"
        procedure.reviewed_by = request.user
        procedure.reviewed_at = timezone.now()
        procedure.review_note = note
        messages.warning(request, f"↩️ تم إعادة الإجراء [{procedure.number}] للمنفذ")

    procedure.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])
    return redirect("procedure_detail", proc_id=proc_id)


@login_required
@require_POST
def upload_evidence(request, proc_id):
    school    = request.user.get_school()
    procedure = get_object_or_404(OperationalProcedure, id=proc_id, school=school)

    if not (request.user.is_admin() or procedure.executor_user == request.user):
        return HttpResponse("غير مسموح", status=403)

    title = request.POST.get("title", "").strip()
    if not title:
        messages.error(request, "عنوان الدليل مطلوب")
        return redirect("procedure_detail", proc_id=proc_id)

    ProcedureEvidence.objects.create(
        procedure=procedure,
        title=title,
        description=request.POST.get("description", "").strip(),
        file=request.FILES.get("file"),
        uploaded_by=request.user,
    )
    messages.success(request, "تم رفع الدليل بنجاح")
    return redirect("procedure_detail", proc_id=proc_id)


# ── قائمة إجراءاتي ──────────────────────────────────────────

@login_required
def my_procedures(request):
    school        = request.user.get_school()
    year          = request.GET.get("year", "2025-2026")
    status_filter = request.GET.get("status", "")

    qs = QualityService.get_my_procedures(request.user, school, year)
    if status_filter:
        qs = qs.filter(status=status_filter)

    total     = qs.count()
    completed = qs.filter(status="Completed").count()
    pct       = round(completed / total * 100) if total else 0

    return render(request, "quality/my_procedures.html", {
        "procedures":     qs,
        "status_filter":  status_filter,
        "STATUS_CHOICES": OperationalProcedure.STATUS,
        "total":          total,
        "completed":      completed,
        "pct":            pct,
        "year":           year,
    })
