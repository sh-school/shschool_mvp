"""
quality/views.py — thin views (Phase 4)
الخطة التشغيلية + اللجنة الموحّدة + ربط المنفذين
"""
from datetime import date as _date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import CustomUser, Membership
from core.pdf_utils import render_pdf

from .models import (
    ExecutorMapping,
    OperationalDomain,
    OperationalProcedure,
    ProcedureEvidence,
    QualityCommitteeMember,
)
from .services import QualityService


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


# ══════════════════════════════════════════════════════════════
# لجنة المراجعة الذاتية
# ══════════════════════════════════════════════════════════════

@login_required
def quality_committee(request):
    school = request.user.get_school()
    year   = request.GET.get("year", "2025-2026")

    staff_ids = Membership.objects.filter(school=school, is_active=True).values_list("user_id", flat=True)

    return render(request, "quality/committee.html", {
        "members":         QualityCommitteeMember.objects.review_committee(school, year),
        "year":            year,
        "committee_type":  QualityCommitteeMember.REVIEW,
        "committee_label": "لجنة المراجعة الذاتية",
        "staff":           CustomUser.objects.filter(id__in=staff_ids).order_by("full_name"),
        "domains":         OperationalDomain.objects.filter(school=school, academic_year=year).order_by("order"),
        "RESP_CHOICES":    QualityCommitteeMember.RESPONSIBILITY,
    })


def _committee_redirect(committee_type, year):
    if committee_type == QualityCommitteeMember.EXECUTOR:
        return f"/quality/executor-committee/?year={year}"
    return f"/quality/committee/?year={year}"


@login_required
@require_POST
def add_committee_member(request):
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school         = request.user.get_school()
    year           = request.POST.get("year", "2025-2026")
    user_id        = request.POST.get("user_id", "").strip()
    job_title      = request.POST.get("job_title", "").strip()
    responsibility = request.POST.get("responsibility", "عضو")
    committee_type = request.POST.get("committee_type", QualityCommitteeMember.REVIEW)
    domain_id      = request.POST.get("domain_id", "").strip() or None

    user   = CustomUser.objects.filter(id=user_id).first() if user_id else None
    domain = OperationalDomain.objects.filter(id=domain_id, school=school).first() if domain_id else None

    if not job_title and not user:
        messages.error(request, "يجب تحديد المستخدم أو المسمى الوظيفي")
        return redirect(_committee_redirect(committee_type, year))

    if not job_title and user:
        job_title = getattr(user, "job_title", "") or str(user)

    QualityCommitteeMember.objects.get_or_create(
        school=school, academic_year=year, user=user, committee_type=committee_type,
        defaults={"job_title": job_title, "responsibility": responsibility, "domain": domain, "is_active": True},
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


# ══════════════════════════════════════════════════════════════
# لجنة منفذي الخطة التشغيلية
# ══════════════════════════════════════════════════════════════

@login_required
def executor_committee(request):
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    year   = request.GET.get("year", "2025-2026")

    data     = QualityService.get_executor_committee_data(school, year)
    staff_ids = Membership.objects.filter(school=school, is_active=True).values_list("user_id", flat=True)

    return render(request, "quality/executor_committee.html", {
        "member_stats":    data["member_stats"],
        "unmapped_norms":  data["unmapped_norms"],
        "year":            year,
        "total_all":       data["overall"]["total"],
        "completed_all":   data["overall"]["completed"],
        "pct_all":         data["overall"]["pct"],
        "committee_type":  QualityCommitteeMember.EXECUTOR,
        "committee_label": "لجنة منفذي الخطة التشغيلية",
        "all_users":       CustomUser.objects.filter(id__in=staff_ids).order_by("full_name"),
    })


@login_required
def executor_member_detail(request, member_id):
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    member = get_object_or_404(
        QualityCommitteeMember, id=member_id, school=school,
        committee_type=QualityCommitteeMember.EXECUTOR,
    )

    year          = request.GET.get("year", "2025-2026")
    status_filter = request.GET.get("status", "")
    domain_filter = request.GET.get("domain", "")

    data = QualityService.get_executor_detail(member, school, year)
    qs   = data["procedures"]

    if status_filter:
        qs = qs.filter(status=status_filter)
    if domain_filter:
        qs = qs.filter(indicator__target__domain__id=domain_filter)

    total     = qs.count()
    completed = qs.filter(status="Completed").count()
    pending   = qs.filter(status="Pending Review").count()
    in_prog   = qs.filter(status="In Progress").count()
    pct       = round(completed / total * 100) if total else 0

    return render(request, "quality/executor_member_detail.html", {
        "member":         member,
        "procedures":     qs,
        "total":          total,
        "completed":      completed,
        "pending":        pending,
        "in_prog":        in_prog,
        "pct":            pct,
        "year":           year,
        "status_filter":  status_filter,
        "domain_filter":  domain_filter,
        "domains":        OperationalDomain.objects.filter(school=school, academic_year=year),
        "STATUS_CHOICES": OperationalProcedure.STATUS,
    })


# ── ربط المنفذين ────────────────────────────────────────────

@login_required
def executor_mapping(request):
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    year   = request.GET.get("year", "2025-2026")

    all_executors = (
        OperationalProcedure.objects.filter(school=school, academic_year=year)
        .values("executor_norm").annotate(proc_count=Count("id")).order_by("executor_norm")
    )

    existing_mappings = {
        m.executor_norm: m
        for m in ExecutorMapping.objects.filter(school=school, academic_year=year).select_related("user")
    }

    staff_ids = Membership.objects.filter(school=school, is_active=True).values_list("user_id", flat=True)
    all_users = CustomUser.objects.filter(id__in=staff_ids).order_by("full_name")

    executor_rows = []
    for row in all_executors:
        norm        = row["executor_norm"]
        mapping     = existing_mappings.get(norm)
        mapped_user = mapping.user if mapping else None

        suggested_user = None
        if not mapped_user and norm and norm.split():
            suggested_user = all_users.filter(full_name__icontains=norm.split()[0]).first()

        executor_rows.append({
            "executor_norm":  norm,
            "proc_count":     row["proc_count"],
            "mapping":        mapping,
            "mapped_user":    mapped_user,
            "user":           mapped_user,
            "is_mapped":      mapped_user is not None,
            "suggested_user": suggested_user,
        })

    mapped_count  = sum(1 for e in executor_rows if e["is_mapped"])

    return render(request, "quality/executor_mapping.html", {
        "executor_rows": executor_rows,
        "staff":         all_users,
        "all_users":     all_users,
        "total":         len(executor_rows),
        "mapped_count":  mapped_count,
        "unmapped_count": len(executor_rows) - mapped_count,
        "year":          year,
    })


@login_required
@require_POST
def save_executor_mapping(request):
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school        = request.user.get_school()
    year          = request.POST.get("year", "2025-2026")
    executor_norm = request.POST.get("executor_norm", "").strip()
    user_id       = request.POST.get("user_id", "").strip()

    if not executor_norm:
        messages.error(request, "المسمى الوظيفي مطلوب")
        return redirect("executor_mapping")

    user    = CustomUser.objects.filter(id=user_id).first() if user_id else None
    mapping, _ = ExecutorMapping.objects.update_or_create(
        school=school, executor_norm=executor_norm, academic_year=year,
        defaults={"user": user},
    )
    mapping.apply_mapping()

    if user:
        proc_count = OperationalProcedure.objects.filter(
            school=school, academic_year=year, executor_norm=executor_norm
        ).count()
        messages.success(request, f"✅ تم ربط [{executor_norm}] بـ {user.full_name} — {proc_count} إجراء مُحدَّث")
    else:
        messages.warning(request, f"تم إلغاء ربط [{executor_norm}]")

    return redirect(f"/quality/executor-mapping/?year={year}")


@login_required
@require_POST
def apply_all_mappings(request):
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school   = request.user.get_school()
    year     = request.POST.get("year", "2025-2026")
    mappings = ExecutorMapping.objects.filter(school=school, academic_year=year, user__isnull=False)
    total    = 0
    for m in mappings:
        total += OperationalProcedure.objects.filter(
            school=school, academic_year=year, executor_norm=m.executor_norm
        ).count()
        m.apply_mapping()

    messages.success(request, f"✅ تم تطبيق {mappings.count()} ربط على {total} إجراء")
    return redirect(f"/quality/executor-mapping/?year={year}")


# ── تقرير التقدم ─────────────────────────────────────────────

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
