"""
quality/views.py
الخطة التشغيلية + لجنة التنفيذ + ربط المنفذين بالمستخدمين
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.db.models import Count, Q, Prefetch
from django.views.decorators.http import require_POST
from django.contrib import messages

from .models import (
    OperationalDomain, OperationalTarget, OperationalIndicator,
    OperationalProcedure, ProcedureEvidence,
    QualityCommitteeMember, ExecutorMapping,
)


# ── لوحة تحكم الخطة التشغيلية ──────────────────────────────

@login_required
def plan_dashboard(request):
    school = request.user.get_school()
    year   = request.GET.get("year", "2025-2026")

    domains = OperationalDomain.objects.filter(
        school=school, academic_year=year
    ).order_by("order")

    total     = OperationalProcedure.objects.filter(school=school, academic_year=year).count()
    completed = OperationalProcedure.objects.filter(school=school, academic_year=year, status="Completed").count()
    in_prog   = OperationalProcedure.objects.filter(school=school, academic_year=year, status="In Progress").count()
    pct       = round(completed / total * 100) if total else 0

    my_procedures = []
    if not request.user.is_admin():
        my_procedures = OperationalProcedure.objects.filter(
            school=school, executor_user=request.user, academic_year=year
        ).select_related("indicator__target__domain").order_by("status", "date_range")

    committee = QualityCommitteeMember.objects.filter(
        school=school, academic_year=year, is_active=True
    ).select_related("user", "domain").order_by("responsibility")

    unmapped_count = 0
    if request.user.is_admin():
        all_executors = set(
            OperationalProcedure.objects.filter(school=school, academic_year=year)
            .values_list("executor_norm", flat=True).distinct()
        )
        mapped = set(
            ExecutorMapping.objects.filter(school=school, academic_year=year, user__isnull=False)
            .values_list("executor_norm", flat=True)
        )
        unmapped_count = len(all_executors - mapped)

    return render(request, "quality/dashboard.html", {
        "domains":        domains,
        "total":          total,
        "completed":      completed,
        "in_progress":    in_prog,
        "pct":            pct,
        "year":           year,
        "committee":      committee,
        "my_procedures":  my_procedures,
        "unmapped_count": unmapped_count,
    })


# ── تفاصيل المجال ───────────────────────────────────────────

@login_required
def domain_detail(request, domain_id):
    school = request.user.get_school()
    domain = get_object_or_404(OperationalDomain, id=domain_id, school=school)

    status_filter   = request.GET.get("status", "")
    executor_filter = request.GET.get("executor", "")

    # ✅ إصلاح N+1 — prefetch كل شيء في 3 queries بدلاً من مئات
    proc_filters = {}
    if status_filter:
        proc_filters['status'] = status_filter
    if executor_filter:
        proc_filters['executor_norm__icontains'] = executor_filter

    indicators_qs = OperationalIndicator.objects.prefetch_related(
        Prefetch(
            'procedures',
            queryset=OperationalProcedure.objects.filter(
                school=school, **proc_filters
            ).select_related('executor_user'),
            to_attr='_filtered_procedures'
        )
    )

    targets = OperationalTarget.objects.filter(
        domain=domain
    ).prefetch_related(
        Prefetch('indicators', queryset=indicators_qs)
    ).order_by("number")

    executors = OperationalProcedure.objects.filter(
        indicator__target__domain=domain
    ).values_list("executor_norm", flat=True).distinct().order_by("executor_norm")

    return render(request, "quality/domain_detail.html", {
        "domain":          domain,
        "targets":         targets,
        "status_filter":   status_filter,
        "executor_filter": executor_filter,
        "executors":       executors,
        "STATUS_CHOICES":  OperationalProcedure.STATUS,
    })


# ── تفاصيل الإجراء + رفع دليل ──────────────────────────────

@login_required
def procedure_detail(request, proc_id):
    school    = request.user.get_school()
    procedure = get_object_or_404(OperationalProcedure, id=proc_id, school=school)
    evidences = procedure.evidences.select_related("uploaded_by").all()

    can_edit = (
        request.user.is_admin()
        or procedure.executor_user == request.user
    )

    return render(request, "quality/procedure_detail.html", {
        "procedure": procedure,
        "evidences": evidences,
        "can_edit":  can_edit,
    })


@login_required
@require_POST
def update_procedure_status(request, proc_id):
    school    = request.user.get_school()
    procedure = get_object_or_404(OperationalProcedure, id=proc_id, school=school)

    can_edit = request.user.is_admin() or procedure.executor_user == request.user
    if not can_edit:
        return HttpResponse("غير مسموح", status=403)

    new_status = request.POST.get("status")
    if new_status in dict(OperationalProcedure.STATUS):
        procedure.status = new_status

    eval_text = request.POST.get("evaluation", "")
    if eval_text:
        procedure.evaluation = eval_text

    procedure.save(update_fields=["status", "evaluation", "updated_at"])

    return render(request, "quality/partials/procedure_status_badge.html", {
        "procedure": procedure
    })


@login_required
@require_POST
def upload_evidence(request, proc_id):
    school    = request.user.get_school()
    procedure = get_object_or_404(OperationalProcedure, id=proc_id, school=school)

    can_edit = request.user.is_admin() or procedure.executor_user == request.user
    if not can_edit:
        return HttpResponse("غير مسموح", status=403)

    title       = request.POST.get("title", "").strip()
    description = request.POST.get("description", "").strip()
    file        = request.FILES.get("file")

    if not title:
        messages.error(request, "عنوان الدليل مطلوب")
        return redirect("procedure_detail", proc_id=proc_id)

    ProcedureEvidence.objects.create(
        procedure=procedure,
        title=title,
        description=description,
        file=file,
        uploaded_by=request.user,
    )
    messages.success(request, "تم رفع الدليل بنجاح")
    return redirect("procedure_detail", proc_id=proc_id)


# ── قائمة إجراءاتي (للمنفذ) ────────────────────────────────

@login_required
def my_procedures(request):
    school        = request.user.get_school()
    year          = request.GET.get("year", "2025-2026")
    status_filter = request.GET.get("status", "")

    qs = OperationalProcedure.objects.filter(
        school=school, executor_user=request.user, academic_year=year
    ).select_related("indicator__target__domain")

    if status_filter:
        qs = qs.filter(status=status_filter)

    qs = qs.order_by("indicator__target__domain__order", "date_range", "number")

    total     = qs.count()
    completed = qs.filter(status="Completed").count()
    pct       = round(completed / total * 100) if total else 0

    mapping_exists = ExecutorMapping.objects.filter(
        school=school, user=request.user, academic_year=year
    ).exists()

    return render(request, "quality/my_procedures.html", {
        "procedures":      qs,
        "total":           total,
        "completed":       completed,
        "pct":             pct,
        "status_filter":   status_filter,
        "STATUS_CHOICES":  OperationalProcedure.STATUS,
        "mapping_exists":  mapping_exists,
    })


# ══════════════════════════════════════════════════════════════
# لجنة تنفيذ الخطة التشغيلية
# ══════════════════════════════════════════════════════════════

@login_required
def quality_committee(request):
    school = request.user.get_school()
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    year    = request.GET.get("year", "2025-2026")
    members = QualityCommitteeMember.objects.filter(
        school=school, academic_year=year, is_active=True
    ).select_related("user", "domain").order_by("responsibility", "job_title")

    domains = OperationalDomain.objects.filter(school=school, academic_year=year).order_by("order")

    from core.models import Membership
    staff_ids = Membership.objects.filter(
        school=school, is_active=True
    ).exclude(role__name="student").values_list("user_id", flat=True)
    from core.models import CustomUser
    staff = CustomUser.objects.filter(id__in=staff_ids).order_by("full_name")

    return render(request, "quality/committee.html", {
        "members":      members,
        "domains":      domains,
        "staff":        staff,
        "year":         year,
        "RESP_CHOICES": QualityCommitteeMember.RESPONSIBILITY,
    })


@login_required
@require_POST
def add_committee_member(request):
    school = request.user.get_school()
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    year       = request.POST.get("year", "2025-2026")
    user_id    = request.POST.get("user_id", "").strip()
    job_title  = request.POST.get("job_title", "").strip()
    resp       = request.POST.get("responsibility", "عضو")
    domain_id  = request.POST.get("domain_id", "")

    from core.models import CustomUser
    user   = CustomUser.objects.filter(id=user_id).first() if user_id else None
    domain = OperationalDomain.objects.filter(id=domain_id, school=school).first() if domain_id else None

    if not job_title and user:
        job_title = user.get_role() or "موظف"

    if not job_title:
        messages.error(request, "المسمى الوظيفي مطلوب")
        return redirect("quality_committee")

    QualityCommitteeMember.objects.create(
        school        = school,
        user          = user,
        job_title     = job_title,
        responsibility= resp,
        domain        = domain,
        academic_year = year,
        is_active     = True,
    )
    messages.success(request, f"تم إضافة {job_title} للجنة")
    return redirect("quality_committee")


@login_required
@require_POST
def remove_committee_member(request, member_id):
    school = request.user.get_school()
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    member = get_object_or_404(QualityCommitteeMember, id=member_id, school=school)
    member.is_active = False
    member.save(update_fields=["is_active"])
    messages.success(request, f"تم إزالة {member.job_title} من اللجنة")
    return redirect("quality_committee")


# ══════════════════════════════════════════════════════════════
# ربط المنفذين بالمستخدمين
# ══════════════════════════════════════════════════════════════

@login_required
def executor_mapping(request):
    school = request.user.get_school()
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    year = request.GET.get("year", "2025-2026")

    all_executors = list(
        OperationalProcedure.objects.filter(school=school, academic_year=year)
        .values_list("executor_norm", flat=True)
        .distinct()
        .order_by("executor_norm")
    )

    mappings = {
        m.executor_norm: m
        for m in ExecutorMapping.objects.filter(
            school=school, academic_year=year
        ).select_related("user")
    }

    proc_counts = dict(
        OperationalProcedure.objects.filter(school=school, academic_year=year)
        .values("executor_norm")
        .annotate(n=Count("id"))
        .values_list("executor_norm", "n")
    )

    executor_rows = []
    for ex in all_executors:
        mapping = mappings.get(ex)
        executor_rows.append({
            "executor_norm": ex,
            "mapping":       mapping,
            "user":          mapping.user if mapping else None,
            "proc_count":    proc_counts.get(ex, 0),
            "is_mapped":     bool(mapping and mapping.user),
        })

    from core.models import Membership, CustomUser
    staff_ids = Membership.objects.filter(
        school=school, is_active=True
    ).exclude(role__name="student").values_list("user_id", flat=True)
    staff = CustomUser.objects.filter(id__in=staff_ids).order_by("full_name")

    mapped_count   = sum(1 for r in executor_rows if r["is_mapped"])
    unmapped_count = len(executor_rows) - mapped_count

    return render(request, "quality/executor_mapping.html", {
        "executor_rows":  executor_rows,
        "staff":          staff,
        "year":           year,
        "total":          len(executor_rows),
        "mapped_count":   mapped_count,
        "unmapped_count": unmapped_count,
    })


@login_required
@require_POST
def save_executor_mapping(request):
    school = request.user.get_school()
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    year          = request.POST.get("year", "2025-2026")
    executor_norm = request.POST.get("executor_norm", "").strip()
    user_id       = request.POST.get("user_id", "").strip()

    if not executor_norm:
        messages.error(request, "المسمى الوظيفي مطلوب")
        return redirect("executor_mapping")

    from core.models import CustomUser
    user = CustomUser.objects.filter(id=user_id).first() if user_id else None

    mapping, _ = ExecutorMapping.objects.update_or_create(
        school=school,
        executor_norm=executor_norm,
        academic_year=year,
        defaults={"user": user},
    )

    mapping.apply_mapping()

    if user:
        proc_count = OperationalProcedure.objects.filter(
            school=school, academic_year=year, executor_norm=executor_norm
        ).count()
        messages.success(request, f"✓ تم ربط [{executor_norm}] بـ {user.full_name} — {proc_count} إجراء مُحدَّث")
    else:
        messages.warning(request, f"تم إلغاء ربط [{executor_norm}]")

    return redirect(f"/quality/executor-mapping/?year={year}")


@login_required
@require_POST
def apply_all_mappings(request):
    school = request.user.get_school()
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    year     = request.POST.get("year", "2025-2026")
    mappings = ExecutorMapping.objects.filter(school=school, academic_year=year, user__isnull=False)
    total    = 0
    for m in mappings:
        count = OperationalProcedure.objects.filter(
            school=school, academic_year=year, executor_norm=m.executor_norm
        ).count()
        m.apply_mapping()
        total += count

    messages.success(request, f"✓ تم تطبيق {mappings.count()} ربط على {total} إجراء")
    return redirect(f"/quality/executor-mapping/?year={year}")


# ── تقرير التقدم الكلي ──────────────────────────────────────

@login_required
def progress_report(request):
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    year   = request.GET.get("year", "2025-2026")

    domains = OperationalDomain.objects.filter(
        school=school, academic_year=year
    ).order_by("order")

    domain_stats = []
    for d in domains:
        procs   = OperationalProcedure.objects.filter(indicator__target__domain=d)
        total   = procs.count()
        done    = procs.filter(status="Completed").count()
        in_prog = procs.filter(status="In Progress").count()
        pct     = round(done / total * 100) if total else 0
        domain_stats.append({
            "domain":      d,
            "total":       total,
            "completed":   done,
            "in_progress": in_prog,
            "pct":         pct,
        })

    executor_stats = OperationalProcedure.objects.filter(
        school=school, academic_year=year
    ).values("executor_norm").annotate(
        total=Count("id"),
        completed=Count("id", filter=Q(status="Completed")),
    ).order_by("-total")[:20]

    return render(request, "quality/progress_report.html", {
        "domain_stats":   domain_stats,
        "executor_stats": executor_stats,
        "year":           year,
    })