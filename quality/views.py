"""
quality/views.py — Core views: لوحة التحكم + المجال + الإجراء
المنطق الثانوي في: views_committee / views_executor / views_reports
"""

from datetime import date as _date

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core.models import AuditLog
from core.permissions import QUALITY_MANAGE, QUALITY_VIEW, role_required
from notifications.hub import NotificationHub

# All roles that can access quality module (view + manage)
_QUALITY_ALL = QUALITY_MANAGE | QUALITY_VIEW | {"ese_teacher"}

from .models import (
    ExecutorMapping,
    OperationalDomain,
    OperationalProcedure,
    ProcedureEvidence,
    ProcedureStatusLog,
    QualityCommitteeMember,
)
from .services import QualityService

# Re-exports for backward compat with urls.py
from .views_committee import (  # noqa: F401
    add_committee_member,
    executor_committee,
    executor_member_detail,
    quality_committee,
    remove_committee_member,
)
from .views_executor import (  # noqa: F401
    apply_all_mappings,
    executor_mapping,
    save_executor_mapping,
)
from .views_reports import progress_report, progress_report_pdf  # noqa: F401


def _safe_next_redirect(request, fallback):
    """تحقق من أن next URL آمن — يمنع Open Redirect."""
    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(next_url)
    return redirect(fallback)


# ── ثوابت ────────────────────────────────────────────────────
_DEFAULT_YEAR = settings.CURRENT_ACADEMIC_YEAR

# Allowed sort fields mapping (GET param → ORM field)
_SORT_FIELDS = {
    "number": "number",
    "domain": "indicator__target__domain__name",
    "target": "indicator__target__number",
    "indicator": "indicator__number",
    "executor": "executor_norm",
    "timing": "date_range",
    "status": "status",
    "follow_up": "follow_up",
}


# ── مساعدات داخلية ───────────────────────────────────────────


def _is_review_member(user, school, year):
    """هل المستخدم عضو نشط في لجنة المراجعة؟ — Clean Code: G5 لا تكرار"""
    return QualityCommitteeMember.objects.filter(
        school=school,
        user=user,
        committee_type=QualityCommitteeMember.REVIEW,
        is_active=True,
    ).exists()


def _can_edit_procedure(user, procedure):
    """هل يملك المستخدم صلاحية تعديل الإجراء؟"""
    return user.is_admin() or procedure.executor_user == user


def _get_reviewer_domain(user, school, year=_DEFAULT_YEAR):
    """الحصول على مجال المراجع (أو None إذا لم يكن مراجعاً)."""
    membership = QualityCommitteeMember.objects.filter(
        school=school,
        user=user,
        committee_type=QualityCommitteeMember.REVIEW,
        is_active=True,
    ).select_related("domain").first()
    return membership.domain if membership else None


def _can_review_procedure(user, school, procedure, year=_DEFAULT_YEAR):
    """هل يحق للمراجع مراجعة هذا الإجراء (مجاله فقط)؟"""
    if user.is_admin():
        return True
    reviewer_domain = _get_reviewer_domain(user, school, year)
    if not reviewer_domain:
        return False
    proc_domain = getattr(procedure, "_cached_domain", None)
    if not proc_domain:
        proc_domain = procedure.indicator.target.domain if procedure.indicator else None
    return proc_domain == reviewer_domain


def _can_view_procedure(user, school, procedure, year=_DEFAULT_YEAR):
    """هل يحق للمستخدم رؤية هذا الإجراء؟"""
    if user.is_admin():
        return True
    if procedure.executor_user == user:
        return True
    return _can_review_procedure(user, school, procedure, year)


def _build_procedure_qs(request, school, year):
    """Build a filtered + sorted queryset shared by execution_list & review_list."""
    qs = OperationalProcedure.objects.filter(school=school, academic_year=year).with_details()

    # ── Filters ──
    field = request.GET.get("field")
    if field:
        qs = qs.filter(indicator__target__domain_id=field)

    target_no = request.GET.get("target_no", "").strip()
    if target_no:
        qs = qs.filter(indicator__target__number__icontains=target_no)

    proced_no = request.GET.get("proced_no", "").strip()
    if proced_no:
        qs = qs.filter(number__icontains=proced_no)

    indicator_no = request.GET.get("indicator_no", "").strip()
    if indicator_no:
        qs = qs.filter(indicator__number__icontains=indicator_no)

    executor = request.GET.get("executor", "").strip()
    if executor:
        qs = qs.filter(executor_norm__icontains=executor)

    timing = request.GET.get("timing", "").strip()
    if timing:
        qs = qs.filter(date_range=timing)

    status = request.GET.get("status", "").strip()
    if status:
        qs = qs.filter(status=status)

    follow_up = request.GET.get("follow_up", "").strip()
    if follow_up:
        qs = qs.filter(follow_up=follow_up)

    evidence_req = request.GET.get("evidence_req", "").strip()
    if evidence_req == "1":
        qs = qs.filter(evidence_request_status="requested")

    # review-specific filters
    review_status = request.GET.get("review_status", "").strip()
    if review_status == "reviewed":
        qs = qs.filter(reviewed_by__isnull=False)
    elif review_status == "not_reviewed":
        qs = qs.filter(reviewed_by__isnull=True)

    evidence_req_status = request.GET.get("evidence_req_status", "").strip()
    if evidence_req_status:
        qs = qs.filter(evidence_request_status=evidence_req_status)

    # ── Sorting ──
    sort = request.GET.get("sort", "number")
    direction = request.GET.get("dir", "asc")
    order_field = _SORT_FIELDS.get(sort, "number")
    if direction == "desc":
        order_field = f"-{order_field}"
    qs = qs.order_by(order_field)

    return qs, sort, direction


def _paginate(request, qs):
    """Paginate queryset; supports per_page=all."""
    per_page_str = request.GET.get("per_page", "25")
    if per_page_str == "all":
        paginator = Paginator(qs, qs.count() or 1)
        return paginator.get_page(1), "all"

    try:
        per_page = int(per_page_str)
        if per_page not in (25, 50, 100):
            per_page = 25
    except (ValueError, TypeError):
        per_page = 25

    paginator = Paginator(qs, per_page)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    return page_obj, per_page


def _list_context(request, school, year, page_obj, per_page, sort, direction):
    """Build shared context dict for execution_list / review_list."""
    timings = (
        OperationalProcedure.objects.filter(school=school, academic_year=year)
        .exclude(date_range="")
        .values_list("date_range", flat=True)
        .distinct()
        .order_by("date_range")
    )

    follow_up_choices = (
        OperationalProcedure.objects.filter(school=school, academic_year=year)
        .exclude(follow_up="")
        .values_list("follow_up", flat=True)
        .distinct()
        .order_by("follow_up")
    )

    return {
        "page_obj": page_obj,
        "fields": OperationalDomain.objects.filter(school=school, academic_year=year),
        "timings": list(timings),
        "status_choices": OperationalProcedure.STATUS,
        "follow_up_choices": list(follow_up_choices),
        "current_per_page": per_page,
        "current_sort": sort,
        "current_dir": direction,
        "year": year,
    }


# ── لوحة تحكم الخطة التشغيلية ──────────────────────────────


@login_required
@role_required(_QUALITY_ALL)
def plan_dashboard(request):
    school = request.user.get_school()
    year = request.GET.get("year", _DEFAULT_YEAR)

    is_admin = request.user.is_admin()
    is_reviewer = _is_review_member(request.user, school, year)
    reviewer_domain = _get_reviewer_domain(request.user, school, year) if is_reviewer else None

    # ── المجالات — المنفذ/المراجع يرى مجالاته فقط ──
    all_domains = OperationalDomain.objects.filter(school=school, academic_year=year).with_progress()
    if is_admin:
        domains = all_domains
    elif is_reviewer and reviewer_domain:
        # المراجع يرى مجاله + مجالات فيها إجراءاته
        my_domain_ids = set()
        my_domain_ids.add(reviewer_domain.pk)
        my_domain_ids.update(
            OperationalProcedure.objects.filter(
                school=school, executor_user=request.user, academic_year=year,
            ).values_list("indicator__target__domain_id", flat=True)
        )
        domains = all_domains.filter(pk__in=my_domain_ids)
    else:
        # المنفذ العادي — يرى فقط مجالات إجراءاته
        my_domain_ids = set(
            OperationalProcedure.objects.filter(
                school=school, executor_user=request.user, academic_year=year,
            ).values_list("indicator__target__domain_id", flat=True)
        )
        domains = all_domains.filter(pk__in=my_domain_ids) if my_domain_ids else all_domains.none()

    # ── الإحصائيات — المدير يرى الكل، المنفذ يرى إجراءاته ──
    if is_admin:
        stats = QualityService.get_plan_stats(school, year)
        base_qs = OperationalProcedure.objects.filter(school=school, academic_year=year)
    elif is_reviewer and reviewer_domain:
        base_qs = OperationalProcedure.objects.filter(
            school=school, academic_year=year,
            indicator__target__domain=reviewer_domain,
        )
        stats = QualityService._calc_stats(base_qs)
        stats["pending_review"] = stats.pop("pending")
    else:
        base_qs = OperationalProcedure.objects.filter(
            school=school, academic_year=year, executor_user=request.user,
        )
        stats = QualityService._calc_stats(base_qs)
        stats["pending_review"] = stats.pop("pending")

    review_committee = QualityCommitteeMember.objects.review_committee(school, year)
    pending_review = base_qs.filter(status="Pending Review").count()
    overdue_count = base_qs.overdue().count()
    evidence_requested = base_qs.filter(evidence_request_status="requested").count()
    unmapped_count = QualityService.get_unmapped_count(school, year) if is_admin else 0

    my_procedures = (
        []
        if is_admin
        else QualityService.get_my_procedures(request.user, school, year)
    )
    return render(
        request,
        "quality/dashboard.html",
        {
            "domains": domains,
            "year": year,
            "review_committee": review_committee,
            "my_procedures": my_procedures,
            "pending_review": pending_review,
            "overdue_count": overdue_count,
            "evidence_requested": evidence_requested,
            "unmapped_count": unmapped_count,
            "is_admin": is_admin,
            "is_reviewer": is_reviewer,
            "reviewer_domain": reviewer_domain,
            **stats,
        },
    )


# ── تفاصيل المجال ───────────────────────────────────────────


@login_required
@role_required(_QUALITY_ALL)
def domain_detail(request, domain_id):
    school = request.user.get_school()
    domain = get_object_or_404(OperationalDomain, id=domain_id, school=school)

    # FIX-06: تقييد الوصول للمجال — المنفذ/المراجع يرى مجاله فقط
    if not request.user.is_admin():
        reviewer_domain = _get_reviewer_domain(request.user, school)
        has_procs = OperationalProcedure.objects.filter(
            school=school, executor_user=request.user,
            indicator__target__domain=domain,
        ).exists()
        if not has_procs and reviewer_domain != domain:
            return HttpResponse("غير مسموح — ليس لديك إجراءات في هذا المجال", status=403)

    status_filter = request.GET.get("status", "")
    executor_filter = request.GET.get("executor", "")

    data = QualityService.get_domain_procedures(school, domain, status_filter, executor_filter)

    return render(
        request,
        "quality/domain_detail.html",
        {
            "domain": domain,
            "targets": data["targets"],
            "executors": data["executors"],
            "status_filter": status_filter,
            "executor_filter": executor_filter,
            "STATUS_CHOICES": OperationalProcedure.STATUS,
        },
    )


# ── تفاصيل الإجراء ──────────────────────────────────────────


@login_required
@role_required(_QUALITY_ALL)
def procedure_detail(request, proc_id):
    school = request.user.get_school()
    procedure = get_object_or_404(
        OperationalProcedure.objects.select_related("indicator__target__domain"),
        id=proc_id, school=school,
    )
    # FIX-06: فحص الدور — المنفذ يرى إجراءه، المراجع يرى مجاله، المدير يرى الكل
    if not _can_view_procedure(request.user, school, procedure):
        return HttpResponse("غير مسموح — لا تملك صلاحية لعرض هذا الإجراء", status=403)
    evidences = procedure.evidences.select_related("uploaded_by").all()

    status_logs = (
        ProcedureStatusLog.objects.filter(
            procedure=procedure,
        )
        .select_related("changed_by")
        .order_by("-created_at")
    )

    return render(
        request,
        "quality/procedure_detail.html",
        {
            "procedure": procedure,
            "evidences": evidences,
            "can_edit": _can_edit_procedure(request.user, procedure),
            "is_reviewer": _is_review_member(
                request.user, school, request.GET.get("year", _DEFAULT_YEAR)
            ),
            "status_logs": status_logs,
            "STATUS_CHOICES": OperationalProcedure.STATUS,
        },
    )


@login_required
@role_required(_QUALITY_ALL)
@require_POST
def update_procedure_status(request, proc_id):
    school = request.user.get_school()
    procedure = get_object_or_404(OperationalProcedure, id=proc_id, school=school)

    if not _can_edit_procedure(request.user, procedure):
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

    procedure.save(
        update_fields=[
            "status",
            "evaluation",
            "deadline",
            "reviewed_at",
            "reviewed_by",
            "updated_at",
        ]
    )

    if new_status == "Pending Review":
        year = request.GET.get("year", _DEFAULT_YEAR)
        review_members = QualityCommitteeMember.objects.review_committee(school, year)
        recipients = [m.user for m in review_members if m.user]
        if recipients:
            NotificationHub.dispatch(
                event_type="plan_update",
                school=school,
                recipients=recipients,
                title=f"إجراء بانتظار المراجعة: {procedure.number}",
                body=f'الإجراء "{procedure.text[:50]}" تم تقديمه للمراجعة',
            )

    return render(request, "quality/partials/procedure_status_badge.html", {"procedure": procedure})


@login_required
@role_required(_QUALITY_ALL)
@require_POST
def approve_procedure(request, proc_id):
    school = request.user.get_school()
    procedure = get_object_or_404(
        OperationalProcedure.objects.select_related("indicator__target__domain"),
        id=proc_id, school=school,
    )
    # FIX-05: فحص المجال — المراجع يعتمد مجاله فقط
    if not _can_review_procedure(request.user, school, procedure):
        return HttpResponse("غير مسموح — لا تملك صلاحية لهذا المجال", status=403)

    action = request.POST.get("action")
    note = request.POST.get("review_note", "").strip()

    if action == "approve":
        procedure.status = "Completed"
        procedure.reviewed_by = request.user
        procedure.reviewed_at = timezone.now()
        procedure.review_note = note
        messages.success(request, f"✅ تم اعتماد الإجراء [{procedure.number}]")
    elif action == "reject":
        procedure.status = "In Progress"
        procedure.reviewed_by = request.user
        procedure.reviewed_at = timezone.now()
        procedure.review_note = note
        messages.warning(request, f"↩️ تم إعادة الإجراء [{procedure.number}] للمنفذ")

    procedure.save(
        update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"]
    )

    # FIX-08: AuditLog
    AuditLog.log(
        user=request.user, action="update", model_name="other",
        object_id=procedure.pk, object_repr=f"Approve/Reject {procedure.number}",
        request=request, changes={"action": action, "status": procedure.status, "note": note},
    )

    if procedure.executor_user:
        new_status = procedure.status
        NotificationHub.dispatch(
            event_type="plan_update",
            school=school,
            recipients=[procedure.executor_user],
            title=f'{"تم اعتماد" if new_status == "Completed" else "تم إعادة"} الإجراء {procedure.number}',
            body=note or "",
        )

    return redirect("procedure_detail", proc_id=proc_id)


@login_required
@role_required(_QUALITY_ALL)
@require_POST
def upload_evidence(request, proc_id):
    school = request.user.get_school()
    procedure = get_object_or_404(OperationalProcedure, id=proc_id, school=school)

    if not _can_edit_procedure(request.user, procedure):
        return HttpResponse("غير مسموح", status=403)

    title = request.POST.get("title", "").strip()
    if not title:
        messages.error(request, "عنوان الدليل مطلوب")
        return redirect("procedure_detail", proc_id=proc_id)

    uploaded_file = request.FILES.get("file")
    # ── HIGH-002 Fix: التحقق من نوع الملف قبل الحفظ ──
    if uploaded_file:
        from django.core.exceptions import ValidationError as DjangoValidationError

        from core.validators import FileTypeValidator

        try:
            FileTypeValidator(allowed_types="document")(uploaded_file)
        except DjangoValidationError as e:
            messages.error(request, e.message)
            return redirect("procedure_detail", proc_id=proc_id)

    QualityService.upload_evidence(
        procedure=procedure,
        title=title,
        description=request.POST.get("description", "").strip(),
        file=uploaded_file,
        uploaded_by=request.user,
    )
    messages.success(request, "تم رفع الدليل بنجاح")
    return redirect("procedure_detail", proc_id=proc_id)


# ── قائمة إجراءاتي ──────────────────────────────────────────


@login_required
@role_required(_QUALITY_ALL)
def my_procedures(request):
    school = request.user.get_school()
    year = request.GET.get("year", _DEFAULT_YEAR)
    status_filter = request.GET.get("status", "")

    qs = QualityService.get_my_procedures(request.user, school, year)
    if status_filter:
        qs = qs.filter(status=status_filter)

    total = qs.count()
    completed = qs.filter(status="Completed").count()
    pct = round(completed / total * 100) if total else 0

    # فحص هل حساب المستخدم مربوط بمنفذ في الخطة
    mapping_exists = ExecutorMapping.objects.filter(
        school=school, user=request.user
    ).exists() or OperationalProcedure.objects.filter(
        school=school, executor_user=request.user, academic_year=year
    ).exists()

    return render(
        request,
        "quality/my_procedures.html",
        {
            "procedures": qs,
            "status_filter": status_filter,
            "STATUS_CHOICES": OperationalProcedure.STATUS,
            "total": total,
            "completed": completed,
            "pct": pct,
            "year": year,
            "mapping_exists": mapping_exists,
        },
    )


# ── قائمة التنفيذ ───────────────────────────────────────────


@login_required
@role_required(QUALITY_MANAGE)
def execution_list(request):
    """قائمة التنفيذ — للمدير فقط (FIX-01: كانت مفتوحة لأي مستخدم)."""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح — للمدير فقط", status=403)

    school = request.user.get_school()
    year = request.GET.get("year", _DEFAULT_YEAR)

    qs, sort, direction = _build_procedure_qs(request, school, year)
    page_obj, per_page = _paginate(request, qs)
    ctx = _list_context(request, school, year, page_obj, per_page, sort, direction)

    return render(request, "quality/execution_list.html", ctx)


@login_required
@role_required(_QUALITY_ALL)
def review_list(request):
    """قائمة المراجعة — لأعضاء لجنة المراجعة والمدير."""
    school = request.user.get_school()
    year = request.GET.get("year", _DEFAULT_YEAR)

    is_admin = request.user.is_admin()
    is_reviewer = _is_review_member(request.user, school, year)

    if not (is_admin or is_reviewer):
        return HttpResponse("غير مسموح", status=403)

    # ── الحصول على مجال العضو (للفلترة التلقائية) ──
    member_domain = None
    if is_reviewer and not is_admin:
        membership = QualityCommitteeMember.objects.filter(
            school=school,
            user=request.user,
            committee_type=QualityCommitteeMember.REVIEW,
            is_active=True,
        ).select_related("domain").first()
        if membership and membership.domain:
            member_domain = membership.domain

    qs, sort, direction = _build_procedure_qs(request, school, year)

    # FIX-02: فلتر المجال إلزامي — لا يمكن تجاوزه بـ ?field=
    if member_domain:
        qs = qs.filter(indicator__target__domain=member_domain)

    page_obj, per_page = _paginate(request, qs)
    ctx = _list_context(request, school, year, page_obj, per_page, sort, direction)
    ctx["evidence_request_choices"] = OperationalProcedure.EVIDENCE_REQUEST_STATUS
    ctx["is_reviewer"] = is_reviewer or is_admin
    ctx["member_domain"] = member_domain

    return render(request, "quality/review_list.html", ctx)


# ── Modal: تحديث الإجراء (HTMX) ─────────────────────────────


def _process_task_update(request, procedure):
    """معالجة POST لتحديث بيانات الإجراء — يفوّض لـ QualityService"""
    uploaded_file = request.FILES.get("evidence_file")
    QualityService.update_procedure_status(
        procedure,
        status=request.POST.get("status", "").strip(),
        evidence_type=request.POST.get("evidence_type", "").strip(),
        evidence_source_file=request.POST.get("evidence_source_file", "").strip(),
        comments=request.POST.get("comments", "").strip(),
        follow_up=request.POST.get("follow_up", "").strip(),
        changed_by=request.user,
        file=uploaded_file,
        file_title=request.POST.get("evidence_title", "").strip(),
    )


@login_required
@role_required(_QUALITY_ALL)
def task_update_modal(request, proc_id):
    """GET: عرض نموذج التحديث — POST: حفظ التغييرات."""
    school = request.user.get_school()
    procedure = get_object_or_404(
        OperationalProcedure.objects.select_related("indicator__target__domain", "executor_user"),
        id=proc_id,
        school=school,
    )

    is_executor = _can_edit_procedure(request.user, procedure)

    # FIX-03: 403 فوري لغير المنفذ والمدير — حتى على GET
    if not is_executor:
        return HttpResponse("غير مسموح — فقط المنفذ المُعيَّن يمكنه التحديث", status=403)

    if request.method == "POST":
        old_status = procedure.status
        _process_task_update(request, procedure)
        AuditLog.log(
            user=request.user, action="update", model_name="other",
            object_id=procedure.pk, object_repr=f"TaskUpdate {procedure.number}",
            request=request, changes={"old_status": old_status, "new_status": procedure.status},
        )
        messages.success(request, "تم تحديث الإجراء بنجاح")
        return _safe_next_redirect(request, "execution_list")

    return render(
        request,
        "quality/modals/task_update.html",
        {
            "task": procedure,
            "indicator": procedure.indicator,
            "follow_up_choices": OperationalProcedure.FOLLOW_UP_CHOICES,
            "status_choices": OperationalProcedure.STATUS,
            "evidence_type_choices": OperationalProcedure.EVIDENCE_TYPE,
            "is_executor": is_executor,
        },
    )


# ── Modal: تقييم المراجعة (HTMX) ────────────────────────────


def _process_review_evaluate(request, procedure):
    """معالجة POST لتقييم المراجعة — يفوّض لـ QualityService"""
    QualityService.review_evaluate(
        procedure,
        evidence_request_status=request.POST.get("evidence_request_status", "").strip(),
        evidence_request_note=request.POST.get("evidence_request_note", "").strip(),
        quality_rating=request.POST.get("quality_rating", "").strip(),
        new_status=request.POST.get("status", "").strip(),
        review_note=request.POST.get("review_note", "").strip(),
        reviewed_by=request.user,
    )


@login_required
@role_required(_QUALITY_ALL)
def review_evaluate_modal(request, proc_id):
    """GET: عرض نموذج تقييم المراجعة — POST: حفظ التقييم."""
    school = request.user.get_school()
    procedure = get_object_or_404(
        OperationalProcedure.objects.select_related(
            "indicator__target__domain", "executor_user", "reviewed_by"
        ).prefetch_related("evidences"),
        id=proc_id,
        school=school,
    )

    # FIX-04: فحص المجال — المراجع يراجع مجاله فقط
    if not _can_review_procedure(request.user, school, procedure):
        return HttpResponse("غير مسموح — هذا الإجراء ليس في مجالك", status=403)

    if request.method == "POST":
        old_status = procedure.status
        _process_review_evaluate(request, procedure)
        AuditLog.log(
            user=request.user, action="update", model_name="other",
            object_id=procedure.pk, object_repr=f"ReviewEvaluate {procedure.number}",
            request=request, changes={
                "old_status": old_status, "new_status": procedure.status,
                "quality_rating": procedure.quality_rating,
                "evidence_request": procedure.evidence_request_status,
            },
        )
        messages.success(request, "تم حفظ تقييم المراجعة بنجاح")
        return _safe_next_redirect(request, "review_list")

    return render(
        request,
        "quality/modals/review_evaluate.html",
        {
            "task": procedure,
            "is_reviewer": True,
            "status_choices": OperationalProcedure.STATUS,
            "evidence_request_choices": OperationalProcedure.EVIDENCE_REQUEST_STATUS,
            "quality_rating_choices": OperationalProcedure.QUALITY_RATING,
        },
    )


# ── تبديل طلب الدليل ─────────────────────────────────────────


@login_required
@role_required(_QUALITY_ALL)
@require_POST
def toggle_evidence_request(request, proc_id):
    """تبديل حالة طلب الدليل بين مطلوب وغير مطلوب."""
    school = request.user.get_school()
    procedure = get_object_or_404(
        OperationalProcedure.objects.select_related("indicator__target__domain"),
        id=proc_id, school=school,
    )
    # FIX-05: فحص المجال — المراجع يطلب أدلة لمجاله فقط
    if not _can_review_procedure(request.user, school, procedure):
        return HttpResponse("غير مسموح — ليس في مجالك", status=403)

    if procedure.evidence_request_status == "requested":
        procedure.evidence_request_status = "not_requested"
    else:
        procedure.evidence_request_status = "requested"

    procedure.save(update_fields=["evidence_request_status", "updated_at"])

    if procedure.evidence_request_status == "requested" and procedure.executor_user:
        NotificationHub.dispatch(
            event_type="plan_update",
            school=school,
            recipients=[procedure.executor_user],
            title=f"مطلوب رفع دليل للإجراء {procedure.number}",
            body=procedure.evidence_request_note or "يرجى رفع الأدلة المطلوبة",
        )

    return _safe_next_redirect(request, "review_list")
