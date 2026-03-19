"""
quality/views.py
الخطة التشغيلية + اللجنة الموحّدة + ربط المنفذين

التغييرات (الإصلاح #4):
- إضافة executor_committee() — واجهة لجنة المنفذين الكاملة
- إضافة executor_member_detail() — تقرير الإنجاز الشخصي لكل منفذ
- إضافة add_executor_member() / remove_executor_member()
- تحديث quality_committee() لدعم committee_type
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.db.models import Count, Q, Prefetch
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils import timezone

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
    pending   = OperationalProcedure.objects.filter(school=school, academic_year=year, status="Pending Review").count()
    pct       = round(completed / total * 100) if total else 0

    my_procedures = []
    if not request.user.is_admin():
        my_procedures = OperationalProcedure.objects.filter(
            school=school, executor_user=request.user, academic_year=year
        ).select_related("indicator__target__domain").order_by("status", "date_range")

    # لجنة المراجعة الذاتية
    review_committee = QualityCommitteeMember.objects.review_committee(school, year)

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
        "domains":           domains,
        "total":             total,
        "completed":         completed,
        "in_progress":       in_prog,
        "pending_review":    pending,
        "pct":               pct,
        "year":              year,
        "review_committee":  review_committee,
        "my_procedures":     my_procedures,
        "unmapped_count":    unmapped_count,
    })


# ── تفاصيل المجال ───────────────────────────────────────────

@login_required
def domain_detail(request, domain_id):
    school = request.user.get_school()
    domain = get_object_or_404(OperationalDomain, id=domain_id, school=school)

    status_filter   = request.GET.get("status", "")
    executor_filter = request.GET.get("executor", "")

    proc_filters = {}
    if status_filter:
        proc_filters["status"] = status_filter
    if executor_filter:
        proc_filters["executor_norm__icontains"] = executor_filter

    indicators_qs = OperationalIndicator.objects.prefetch_related(
        Prefetch(
            "procedures",
            queryset=OperationalProcedure.objects.filter(
                school=school, **proc_filters
            ).select_related("executor_user"),
            to_attr="_filtered_procedures",
        )
    )

    targets = OperationalTarget.objects.filter(
        domain=domain
    ).prefetch_related(
        Prefetch("indicators", queryset=indicators_qs)
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

    # هل المستخدم عضو في لجنة المراجعة؟
    is_reviewer = QualityCommitteeMember.objects.filter(
        school=school,
        user=request.user,
        committee_type=QualityCommitteeMember.REVIEW,
        is_active=True,
    ).exists()

    return render(request, "quality/procedure_detail.html", {
        "procedure":    procedure,
        "evidences":    evidences,
        "can_edit":     can_edit,
        "is_reviewer":  is_reviewer,
        "STATUS_CHOICES": OperationalProcedure.STATUS,
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

    # إذا انتقل لـ "Pending Review" سجّل الوقت
    if new_status == "Pending Review":
        procedure.reviewed_at = None
        procedure.reviewed_by = None

    procedure.save(update_fields=["status", "evaluation", "reviewed_at", "reviewed_by", "updated_at"])

    return render(request, "quality/partials/procedure_status_badge.html", {
        "procedure": procedure
    })


@login_required
@require_POST
def approve_procedure(request, proc_id):
    """لجنة المراجعة تعتمد أو ترفض الإجراء"""
    school    = request.user.get_school()
    procedure = get_object_or_404(OperationalProcedure, id=proc_id, school=school)

    is_reviewer = QualityCommitteeMember.objects.filter(
        school=school,
        user=request.user,
        committee_type=QualityCommitteeMember.REVIEW,
        is_active=True,
        can_review=True,
    ).exists()

    if not (request.user.is_admin() or is_reviewer):
        return HttpResponse("غير مسموح", status=403)

    action = request.POST.get("action")  # "approve" أو "reject"
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

    qs = qs.order_by("status", "date_range")

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
    """عرض أعضاء لجنة المراجعة الذاتية"""
    school = request.user.get_school()
    year   = request.GET.get("year", "2025-2026")

    members = QualityCommitteeMember.objects.review_committee(school, year)

    return render(request, "quality/committee.html", {
        "members":        members,
        "year":           year,
        "committee_type": QualityCommitteeMember.REVIEW,
        "committee_label": "لجنة المراجعة الذاتية",
    })


@login_required
@require_POST
def add_committee_member(request):
    """إضافة عضو للجنة (مراجعة أو تنفيذية)"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school         = request.user.get_school()
    year           = request.POST.get("year", "2025-2026")
    user_id        = request.POST.get("user_id", "").strip()
    job_title      = request.POST.get("job_title", "").strip()
    responsibility = request.POST.get("responsibility", "عضو")
    committee_type = request.POST.get("committee_type", QualityCommitteeMember.REVIEW)
    domain_id      = request.POST.get("domain_id", "").strip() or None

    from core.models import CustomUser
    user = CustomUser.objects.filter(id=user_id).first() if user_id else None

    domain = None
    if domain_id:
        domain = OperationalDomain.objects.filter(id=domain_id, school=school).first()

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
            "job_title":      job_title,
            "responsibility": responsibility,
            "domain":         domain,
            "is_active":      True,
        },
    )

    messages.success(request, f"✅ تم إضافة {job_title} للجنة")
    return redirect(_committee_redirect(committee_type, year))


@login_required
@require_POST
def remove_committee_member(request, member_id):
    """إزالة عضو من اللجنة"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    member = get_object_or_404(QualityCommitteeMember, id=member_id, school=school)
    committee_type = member.committee_type
    year           = member.academic_year
    member.delete()

    messages.success(request, "تم إزالة العضو من اللجنة")
    return redirect(_committee_redirect(committee_type, year))


def _committee_redirect(committee_type, year):
    if committee_type == QualityCommitteeMember.EXECUTOR:
        return f"/quality/executor-committee/?year={year}"
    return f"/quality/committee/?year={year}"


# ══════════════════════════════════════════════════════════════
# لجنة منفذي الخطة التشغيلية — الإصلاح #4 (جديد كلياً)
# ══════════════════════════════════════════════════════════════

@login_required
def executor_committee(request):
    """
    لوحة تحكم لجنة منفذي الخطة التشغيلية.
    تعرض:
    - قائمة الأعضاء مع إحصائيات إنجازهم
    - إجراءات كل عضو مصنّفة بالحالة
    - نسبة إنجاز كل منفذ
    """
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    year   = request.GET.get("year", "2025-2026")

    # أعضاء اللجنة التنفيذية
    members = QualityCommitteeMember.objects.executor_committee(school, year)

    # إحصائيات كل عضو
    member_stats = []
    for member in members:
        if member.user:
            procs = OperationalProcedure.objects.filter(
                school=school,
                executor_user=member.user,
                academic_year=year,
            )
            total     = procs.count()
            completed = procs.filter(status="Completed").count()
            pending   = procs.filter(status="Pending Review").count()
            in_prog   = procs.filter(status="In Progress").count()
            pct       = round(completed / total * 100) if total else 0
            member_stats.append({
                "member":    member,
                "total":     total,
                "completed": completed,
                "pending":   pending,
                "in_prog":   in_prog,
                "pct":       pct,
            })
        else:
            # عضو بدون مستخدم مربوط
            member_stats.append({
                "member":    member,
                "total":     0,
                "completed": 0,
                "pending":   0,
                "in_prog":   0,
                "pct":       0,
                "unmapped":  True,
            })

    # الإحصائيات الكلية
    all_procs = OperationalProcedure.objects.filter(school=school, academic_year=year)
    total_all     = all_procs.count()
    completed_all = all_procs.filter(status="Completed").count()
    pct_all       = round(completed_all / total_all * 100) if total_all else 0

    # المنفذون غير المسنَدين بعد (executor_norm بدون user)
    all_norms = set(
        all_procs.values_list("executor_norm", flat=True).distinct()
    )
    mapped_norms = set(
        ExecutorMapping.objects.filter(school=school, academic_year=year, user__isnull=False)
        .values_list("executor_norm", flat=True)
    )
    unmapped_norms = all_norms - mapped_norms

    return render(request, "quality/executor_committee.html", {
        "member_stats":    member_stats,
        "year":            year,
        "total_all":       total_all,
        "completed_all":   completed_all,
        "pct_all":         pct_all,
        "unmapped_norms":  unmapped_norms,
        "committee_type":  QualityCommitteeMember.EXECUTOR,
        "committee_label": "لجنة منفذي الخطة التشغيلية",
    })


@login_required
def executor_member_detail(request, member_id):
    """
    تقرير الإنجاز الشخصي لمنفذ واحد.
    يعرض جميع إجراءاته مع إمكانية تصفيتها بالحالة والمجال.
    """
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    member = get_object_or_404(
        QualityCommitteeMember,
        id=member_id,
        school=school,
        committee_type=QualityCommitteeMember.EXECUTOR,
    )

    year          = request.GET.get("year", "2025-2026")
    status_filter = request.GET.get("status", "")
    domain_filter = request.GET.get("domain", "")

    qs = OperationalProcedure.objects.filter(
        school=school,
        academic_year=year,
    )

    if member.user:
        qs = qs.filter(executor_user=member.user)
    else:
        qs = qs.filter(executor_norm=member.job_title)

    if status_filter:
        qs = qs.filter(status=status_filter)
    if domain_filter:
        qs = qs.filter(indicator__target__domain__id=domain_filter)

    qs = qs.select_related(
        "indicator__target__domain", "executor_user"
    ).order_by("indicator__target__domain__name", "status", "number")

    # إحصائيات
    total     = qs.count()
    completed = qs.filter(status="Completed").count()
    pending   = qs.filter(status="Pending Review").count()
    in_prog   = qs.filter(status="In Progress").count()
    pct       = round(completed / total * 100) if total else 0

    # المجالات المتاحة للفلتر
    domains = OperationalDomain.objects.filter(school=school, academic_year=year)

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
        "domains":        domains,
        "STATUS_CHOICES": OperationalProcedure.STATUS,
    })


# ── ربط المنفذين ────────────────────────────────────────────

@login_required
def executor_mapping(request):
    school = request.user.get_school()
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    year = request.GET.get("year", "2025-2026")

    all_executors = (
        OperationalProcedure.objects.filter(school=school, academic_year=year)
        .values("executor_norm")
        .annotate(proc_count=Count("id"))
        .order_by("executor_norm")
    )

    existing_mappings = {
        m.executor_norm: m
        for m in ExecutorMapping.objects.filter(
            school=school, academic_year=year
        ).select_related("user")
    }

    from core.models import CustomUser
    all_users = CustomUser.objects.filter(school=school).order_by("full_name")

    executor_data = []
    for row in all_executors:
        norm    = row["executor_norm"]
        mapping = existing_mappings.get(norm)
        executor_data.append({
            "executor_norm": norm,
            "proc_count":    row["proc_count"],
            "mapping":       mapping,
            "mapped_user":   mapping.user if mapping else None,
        })

    unmapped_count = sum(1 for e in executor_data if not e["mapped_user"])

    return render(request, "quality/executor_mapping.html", {
        "executor_data":   executor_data,
        "all_users":       all_users,
        "unmapped_count":  unmapped_count,
        "year":            year,
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
        messages.success(
            request,
            f"✅ تم ربط [{executor_norm}] بـ {user.full_name} — {proc_count} إجراء مُحدَّث",
        )
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

    messages.success(request, f"✅ تم تطبيق {mappings.count()} ربط على {total} إجراء")
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
        pending = procs.filter(status="Pending Review").count()
        pct     = round(done / total * 100) if total else 0
        domain_stats.append({
            "domain":         d,
            "total":          total,
            "completed":      done,
            "in_progress":    in_prog,
            "pending_review": pending,
            "pct":            pct,
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
