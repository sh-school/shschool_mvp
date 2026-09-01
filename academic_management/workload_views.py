"""شاشاتُ خطّة النصاب: قراءةٌ في مسار، وأوامرُ في مسارات.

    /academic/workload/                      مرصدٌ للمدرسة كلّها — قراءةٌ محضة
    /academic/workload/teacher/<id>/         بطاقةُ معلّمٍ واحد — قراءة
    /academic/workload/plan/<id>/edit/       محرّرُ خطّةٍ واحدة
    /academic/workload/plan/<id>/<command>/  أمرٌ واحدٌ بـPOST واحد

ولا تعرف هذه الوحدةُ منطقَ الانتقالات. زرُّ الاعتماد لا يكتب
`plan.status = APPROVED`؛ يستدعي `workload_workflow.approve(...)` ويعرض ما
يقوله. فالبوّابةُ والتوقيعُ والتجاوزُ المسجَّلُ كلُّها في الخدمة، ولو نسخنا
سطراً منها هنا لصار في النظام مصدرانِ لقرارٍ واحد.

والإسنادُ الحاليُّ معروضٌ في المحرّر وغيرُ قابلٍ للتحرير فيه: معالجةُ فرقِ
«١٤ من ١٦» تكون في إسناد الموادّ، لا في خطّة النصاب. وخلطُ العمليّتين في
شاشةٍ واحدةٍ يُغري بتعديل الواقع كي يوافق الورقة.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from academic_management import workload_workflow as flow
from academic_management.models import (
    APPROVED,
    DRAFT,
    FROM_MANUAL,
    LOCKED,
    REVIEWED,
    SUBMITTED,
    TeacherSubjectQualification,
    TeacherWorkloadAllocation,
    TeacherWorkloadPlan,
)
from academic_management.workload_forms import (
    AllocationForm,
    PlanHeadForm,
    QualificationForm,
    ReductionForm,
)
from core.academic_calendar import academic_year_for

MODULE_NAME = "إدارة الشؤون الأكاديمية"


# ══════════════════════════════════════════════════════════════════════
#  أدواتٌ مشتركة
# ══════════════════════════════════════════════════════════════════════


def _school(request):
    school = request.user.get_school() if hasattr(request.user, "get_school") else None
    if school is None:
        raise Http404("لا مدرسةَ نشطةٌ لهذا المستخدم.")
    return school


def _plan(request, plan_id):
    """خطّةٌ من مدرسة المستخدم — وخطّةُ غيرها لا يُكشف وجودُها.

    و`404` هنا مقصودة: `403` على خطّةٍ في مدرسةٍ أخرى تُخبر السائلَ أنّها
    موجودة، وهذا تسريبٌ صغيرٌ يكفي لعدّ المدارس ومعرفة معلّميها.
    """
    return get_object_or_404(
        TeacherWorkloadPlan.objects.select_related("teacher", "school"),
        pk=plan_id,
        school=_school(request),
    )


def _teacher(request, teacher_id):
    from core.models import CustomUser

    school = _school(request)
    return get_object_or_404(
        CustomUser.objects.filter(memberships__school=school, memberships__is_active=True)
        .distinct(),
        pk=teacher_id,
    )


def _command(request, plan, action, success):
    """يُشغّل أمراً من الخدمة ويترجم أخطاءَ المجال إلى رسائل — لا إلى 500."""
    try:
        action()
    except flow.WorkflowError as exc:
        messages.error(request, str(exc))
    except ValidationError as exc:
        messages.error(request, "؛ ".join(exc.messages))
    else:
        messages.success(request, success)
    return redirect("academic_management:plan_editor", plan_id=plan.pk)


# ══════════════════════════════════════════════════════════════════════
#  القراءة
# ══════════════════════════════════════════════════════════════════════


@login_required
def teacher_workload(request, teacher_id):
    """بطاقةُ معلّمٍ واحد: نسخُ خطّته، والمعتمَدُ منها، وأين يقف الإسنادُ منه."""
    school = _school(request)
    teacher = _teacher(request, teacher_id)
    year = request.GET.get("year") or academic_year_for(request)

    plans = list(
        TeacherWorkloadPlan.objects.filter(
            school=school, teacher=teacher, academic_year=year
        ).order_by("-plan_version")
    )
    current = TeacherWorkloadPlan.current_for(school, teacher, year)

    return render(
        request,
        "academic_management/workload_teacher.html",
        {
            "page_title": f"نصاب {teacher.full_name}",
            "module_name": MODULE_NAME,
            "teacher": teacher,
            "year": year,
            "plans": plans,
            "current": current,
            "diverged": flow.has_diverged(current) if current else None,
            "assigned": flow.assigned_periods(current) if current else None,
            "can_edit": flow.has_capability(request.user, school, flow.EDIT),
        },
    )


@login_required
def plan_editor(request, plan_id):
    """محرّرُ الخطّة بترتيبه: نصابٌ، فتخفيضٌ، فهدفٌ محسوب، فتوزيعٌ، فمؤهّلات،
    فإسنادٌ للقراءة، فبوّابةٌ بنداً بنداً."""
    plan = _plan(request, plan_id)
    return render(
        request, "academic_management/workload_editor.html", _editor_context(request, plan)
    )


def _editor_context(request, plan):
    """سياقُ المحرّر بالاستمارات الفارغة — ومن أعادها بأخطائها يستبدلها وحدَها."""
    school = plan.school
    return {
        "page_title": f"خطّة نصاب — {plan.teacher.full_name}",
        "module_name": MODULE_NAME,
        "plan": plan,
        "editable": flow.is_editable(plan),
        "head_form": PlanHeadForm(instance=plan),
        "reduction_form": ReductionForm(instance=plan),
        "allocation_form": AllocationForm(plan=plan),
        "qualification_form": QualificationForm(school=school, teacher=plan.teacher),
        "allocations": plan.allocations.all(),
        "allocated": sum(a.target_periods for a in plan.allocations.all()),
        "qualifications": TeacherSubjectQualification.objects.filter(
            school=school, teacher=plan.teacher
        ).select_related("subject"),
        "assigned": flow.assigned_periods(plan),
        "capacity": flow.available_capacity(plan),
        "checks": flow.validate(plan),
        "can_edit": flow.has_capability(request.user, school, flow.EDIT),
        "can_review": flow.has_capability(request.user, school, flow.REVIEW),
        "can_approve": flow.has_capability(request.user, school, flow.APPROVE),
    }


@login_required
def plan_review(request, plan_id):
    """منظورُ المراجع: النسخةُ المقترحةُ إلى جانب المعتمَدةِ قبلها.

    فالمراجعُ لا يسأل «هل هذا الرقمُ سليم؟» بل «ما الذي تغيّر ولماذا؟»، وعرضُ
    النسخة الجديدة وحدَها يُخفي السؤالَ الثاني.
    """
    plan = _plan(request, plan_id)
    previous = (
        TeacherWorkloadPlan.objects.filter(
            school=plan.school,
            teacher=plan.teacher,
            academic_year=plan.academic_year,
            status__in=(APPROVED, LOCKED),
        )
        .exclude(pk=plan.pk)
        .order_by("-plan_version")
        .first()
    )
    return render(
        request,
        "academic_management/workload_review.html",
        {
            "page_title": f"مراجعة نصاب — {plan.teacher.full_name}",
            "module_name": MODULE_NAME,
            "plan": plan,
            "previous": previous,
            "rows": _comparison(previous, plan),
            "qualification_rows": _qualification_comparison(plan),
            "checks": flow.validate(plan),
            "can_review": flow.has_capability(request.user, plan.school, flow.REVIEW),
            "can_approve": flow.has_capability(request.user, plan.school, flow.APPROVE),
        },
    )


def _levels(plan):
    return {a.level_type: a.target_periods for a in plan.allocations.all()}


def _comparison(previous, proposed):
    """جدولُ «قبل ← بعد» — وغيابُ سابقةٍ يُقال صراحةً لا يُملأ بصفر."""
    old_levels = _levels(previous) if previous else {}
    new_levels = _levels(proposed)
    rows = [
        ("النصاب", previous.required_weekly_periods if previous else None,
         proposed.required_weekly_periods),
        ("التخفيض", previous.reduction_periods if previous else None,
         proposed.reduction_periods),
        ("الهدف التدريسيّ", previous.teaching_target if previous else None,
         proposed.teaching_target),
    ]
    for level, label in (("prep", "إعدادي"), ("sec", "ثانوي")):
        if level in old_levels or level in new_levels:
            rows.append((label, old_levels.get(level), new_levels.get(level)))
    return [
        {"label": label, "before": before, "after": after, "changed": before != after}
        for label, before, after in rows
    ]


def _qualification_comparison(plan):
    """المؤهّلاتُ الساريةُ ومن غيرِها — فتغيّرُها تغيّرٌ في الخطّة أيضاً."""
    return [
        {
            "subject": q.subject,
            "scope": q.get_level_type_display() if q.level_type else "كلّ المراحل",
            "status": q.get_qualification_status_display(),
            "reference": q.source_reference,
            "valid": q.is_valid_on(),
        }
        for q in TeacherSubjectQualification.objects.filter(
            school=plan.school, teacher=plan.teacher
        ).select_related("subject")
    ]


# ══════════════════════════════════════════════════════════════════════
#  الأوامر — كلُّها POST، وكلُّها تستدعي الخدمة
# ══════════════════════════════════════════════════════════════════════


@login_required
@require_POST
def open_draft(request, teacher_id):
    school = _school(request)
    teacher = _teacher(request, teacher_id)
    year = request.POST.get("year") or academic_year_for(request)
    try:
        plan = flow.open_draft(
            school,
            teacher,
            year,
            by=request.user,
            required_weekly_periods=0,
            required_source_kind=FROM_MANUAL,
            required_source_reference="",
        )
    except ValidationError as exc:
        messages.error(request, "؛ ".join(exc.messages))
        return redirect("academic_management:teacher_workload", teacher_id=teacher_id)
    messages.success(request, "فُتحت مسودّةُ نصاب — املأ النصابَ ومرجعَه.")
    return redirect("academic_management:plan_editor", plan_id=plan.pk)


#: أيُّ خانةٍ في سياق المحرّر تحمل كلَّ استمارة حين تُعاد بأخطائها.
_SECTION_CONTEXT = {}


def _stale(form):
    return "seen_at" in form.errors


def _save_section(request, plan, form_class, kwargs, success):
    """يحفظ قسماً واحداً من المحرّر — ويرفض الكتابةَ فوق ما تغيّر بعد فتحه.

    والحالتان مفرّقتان قصداً: `409` تقول «سبقك غيرُك فأعِد القراءة»، و`422`
    تقول «مدخلاتُك هي التي لا تستقيم». وجمعُهما في رمزٍ واحدٍ يُضيّع الفرق.
    """
    flow.require(request.user, plan.school, flow.EDIT)
    if not flow.is_editable(plan):
        messages.error(request, "لا تُحرَّر إلّا المسودّة — رُدّها إلى المسودّة أوّلاً.")
        return redirect("academic_management:plan_editor", plan_id=plan.pk)

    form = form_class(request.POST, **kwargs)
    if not form.is_valid():
        context = _editor_context(request, plan)
        context[_SECTION_CONTEXT[form_class]] = form
        return render(
            request,
            "academic_management/workload_editor.html",
            context,
            status=409 if _stale(form) else 422,
        )

    obj = form.save(commit=False)
    obj.updated_by = request.user
    obj.save()
    messages.success(request, success)
    return redirect("academic_management:plan_editor", plan_id=plan.pk)


@login_required
@require_POST
def edit_head(request, plan_id):
    plan = _plan(request, plan_id)
    return _save_section(
        request, plan, PlanHeadForm, {"instance": plan}, "حُفظ النصابُ ومرجعُه."
    )


@login_required
@require_POST
def edit_reduction(request, plan_id):
    plan = _plan(request, plan_id)
    return _save_section(
        request, plan, ReductionForm, {"instance": plan}, "حُفظ التخفيضُ ومرجعُه."
    )


@login_required
@require_POST
def add_allocation(request, plan_id):
    plan = _plan(request, plan_id)
    return _save_section(
        request, plan, AllocationForm, {"plan": plan}, "أُضيف توزيعُ المرحلة."
    )


@login_required
@require_POST
def delete_allocation(request, plan_id, allocation_id):
    plan = _plan(request, plan_id)
    flow.require(request.user, plan.school, flow.EDIT)
    if not flow.is_editable(plan):
        messages.error(request, "لا تُحرَّر إلّا المسودّة.")
    else:
        get_object_or_404(
            TeacherWorkloadAllocation, pk=allocation_id, workload_plan=plan
        ).delete()
        messages.success(request, "حُذف توزيعُ المرحلة.")
    return redirect("academic_management:plan_editor", plan_id=plan.pk)


@login_required
@require_POST
def add_qualification(request, plan_id):
    plan = _plan(request, plan_id)
    return _save_section(
        request,
        plan,
        QualificationForm,
        {"school": plan.school, "teacher": plan.teacher},
        "أُضيف المؤهّلُ بمرجعه.",
    )


@login_required
def validate_plan(request, plan_id):
    """بوّابةُ التحقّق بنداً بنداً — تشخيصٌ لا حكمٌ واحد.

    و«الخطّةُ غيرُ صالحة» جملةٌ لا تُصلح شيئاً؛ أمّا «الإسنادُ ١٤ من ١٦»
    فتقول للمُدخِل أين يذهب.
    """
    plan = _plan(request, plan_id)
    checks = flow.validate(plan)
    return render(
        request,
        "academic_management/workload_gate.html",
        {
            "page_title": f"تحقّقٌ — {plan.teacher.full_name}",
            "module_name": MODULE_NAME,
            "plan": plan,
            "checks": checks,
            "blocking": flow.blocking(checks),
        },
    )


@login_required
@require_POST
def submit_plan(request, plan_id):
    plan = _plan(request, plan_id)
    flow.require(request.user, plan.school, flow.EDIT)
    return _command(
        request, plan, lambda: flow.submit_for_review(plan, by=request.user), "رُفعت للمراجعة."
    )


@login_required
@require_POST
def review_plan(request, plan_id):
    plan = _plan(request, plan_id)
    flow.require(request.user, plan.school, flow.REVIEW)
    comment = request.POST.get("comment", "")
    return _command(
        request, plan, lambda: flow.record_review(plan, by=request.user, comment=comment),
        "سُجّلت المراجعة.",
    )


@login_required
@require_POST
def return_plan(request, plan_id):
    plan = _plan(request, plan_id)
    flow.require(request.user, plan.school, flow.REVIEW)
    comment = request.POST.get("comment", "")
    return _command(
        request, plan, lambda: flow.return_to_draft(plan, by=request.user, comment=comment),
        "رُدّت إلى المسودّة.",
    )


@login_required
@require_POST
def approve_plan(request, plan_id):
    """الاعتماد — والـview لا يعرف منه إلّا اسمَه."""
    plan = _plan(request, plan_id)
    flow.require(request.user, plan.school, flow.APPROVE)
    try:
        flow.approve(plan, by=request.user)
    except PermissionDenied as exc:
        messages.error(request, str(exc))
    except flow.WorkflowError as exc:
        messages.error(request, str(exc))
    except ValidationError as exc:
        messages.error(request, "؛ ".join(exc.messages))
    else:
        messages.success(request, "اعتُمدت الخطّة، وحُفظت بصمةُ الإسناد الذي فُحص.")
    return redirect("academic_management:plan_editor", plan_id=plan.pk)


@login_required
@require_POST
def lock_plan(request, plan_id):
    plan = _plan(request, plan_id)
    flow.require(request.user, plan.school, flow.APPROVE)
    return _command(request, plan, lambda: flow.lock(plan, by=request.user), "أُقفلت للجدولة.")


@login_required
@require_POST
def revise_plan(request, plan_id):
    """إصدارٌ جديدٌ عن نسخةٍ معتمَدة — والقديمةُ تبقى قائمةً كما اعتُمدت."""
    plan = _plan(request, plan_id)
    flow.require(request.user, plan.school, flow.EDIT)
    try:
        fresh = flow.new_version_from(plan, by=request.user)
    except flow.WorkflowError as exc:
        messages.error(request, str(exc))
        return redirect("academic_management:plan_editor", plan_id=plan.pk)
    except ValidationError as exc:
        messages.error(request, "؛ ".join(exc.messages))
        return redirect("academic_management:plan_editor", plan_id=plan.pk)
    messages.success(request, f"فُتح الإصدارُ {fresh.plan_version} مسودّةً.")
    return redirect("academic_management:plan_editor", plan_id=fresh.pk)


_SECTION_CONTEXT.update(
    {
        PlanHeadForm: "head_form",
        ReductionForm: "reduction_form",
        AllocationForm: "allocation_form",
        QualificationForm: "qualification_form",
    }
)


#: تُستعمل في القوالب لتلوين الحالة.
STATUS_TONE = {
    DRAFT: "muted",
    SUBMITTED: "info",
    REVIEWED: "info",
    APPROVED: "ok",
    LOCKED: "ok",
}
