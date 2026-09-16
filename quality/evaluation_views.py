"""
quality/evaluation_views.py
Phase 6 — واجهات تقييم الموظفين
المرجع: النظام الوظيفي لموظفي المدارس (قرار مجلس الوزراء 32/2019) المواد 15–21
(02_staff_affairs.md:199-215)، والاستمارات السبع (06_attendance_performance_review.md §2).
وكان الرأسُ يُسند إلى «القرار الأميري 9/2016» ولا أثرَ له في المصدر.

إصلاح: ربط RoleEvaluationTemplate + EvaluationScore + قائمة الموظفين
"""

from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.academic_calendar import academic_year_for, default_academic_year
from core.capabilities import capability_required
from core.models import AuditLog, CustomUser, Membership
from core.models.user import role_rank

from .appraisal_forms import forms_by_role
from .evaluation_services import (
    PRINCIPAL_NOT_EVALUATED,
    SELF_EVALUATION,
    EvaluationRejectedError,
    annual_rating_summary,
    axis_values,
    is_academic_year,
    is_school_principal,
    record_receipt_on_refusal,
    save_evaluation,
)
from .evaluation_services import approve_evaluation as approve_evaluation_service
from .models import (
    _EVALUABLE_ROLES,
    EmployeeEvaluation,
    EvaluationCycle,
    RoleEvaluationTemplate,
)
from .presentation import evaluation_rating_tone, evaluation_status_tone


#: يُقرأ وقت الطلب لا وقت الاستيراد — ثابتُ الوحدة يتجمّد عند إقلاع العملية.
def _default_year(request=None):
    return academic_year_for(request) if request is not None else default_academic_year()


# المحاور الافتراضية (تُستخدم عندما لا يوجد قالب مخصص)
_DEFAULT_AXES = [
    ("axis_professional", "الكفاءة المهنية", 25),
    ("axis_commitment", "الالتزام والمسؤولية", 25),
    ("axis_teamwork", "العمل الجماعي والتواصل", 25),
    ("axis_development", "التطوير المهني والمبادرة", 25),
]


def _require_evaluator(request):
    """فقط المدير والنائبان يقيّمون"""
    return request.user.is_admin() or request.user.get_role() in (
        "vice_admin",
        "vice_academic",
    )


def _get_employee_role(school, employee):
    """
    الدورُ الحاكمُ للموظّف في المدرسة، بترتيب `CustomUser.active_memberships` نفسِه. كان
    `.first()` بلا ترتيب، فصاحبُ العضويّتين يُقيَّم على استمارة أيٍّ منهما اتّفق.
    """
    membership = (
        Membership.objects.filter(school=school, user=employee, is_active=True)
        .select_related("role")
        .order_by(role_rank(), "joined_at", "id")
        .first()
    )
    return membership.role.name if membership else None


def _get_axes_for_employee(school, employee, year):
    """
    الحصول على محاور التقييم حسب دور الموظف.
    إذا وُجد قالبٌ هو استمارةُ دوره (`matches_ministry_form`) → محاور القالب.
    وإلا → المحاور الأربعة الافتراضية — فلا يُفتح عليها تقريرٌ سنويّ (المادة 15،
    02_staff_affairs.md:199: «وفقاً للنماذج المعتمدة من الوزير»).
    """
    role_name = _get_employee_role(school, employee)
    if role_name:
        template = (
            RoleEvaluationTemplate.objects.filter(
                school=school, role_name=role_name, academic_year=year, is_active=True
            )
            .prefetch_related("axes")
            .first()
        )
        if template and template.matches_ministry_form():
            return (
                [(a.key, a.label, a.weight) for a in template.axes.all()],
                template,
            )
    return _DEFAULT_AXES, None


def _s2_blocked_reason(role_name, seeded_roles):
    """
    لماذا لا يُفتح التقريرُ السنويّ لهذا الدور — أو "" إن كان يُفتح. هو ما يردّ به
    `create_evaluation` 409، فيُعرض في الصفّ نصّاً بدل زرٍّ يُفضي إلى صفحةٍ خامّة.
    """
    if role_name in seeded_roles:
        return ""
    if role_name in forms_by_role():
        return "الاستمارة غير مبذورة لهذا العام"
    # المادة 15: «وفقاً للنماذج المعتمدة من الوزير» — ولا استمارةَ مسمّاةً للدور (ADR-0002 §6.6).
    return "لا استمارة وزاريّة للدور — معلّقٌ للمالك"


def _get_evaluable_staff(school, year, viewer=None):
    """قائمة الموظفين القابلين للتقييم مع حالة التقييم"""
    memberships = (
        Membership.objects.filter(school=school, is_active=True, role__name__in=_EVALUABLE_ROLES)
        .select_related("user", "role")
        .order_by("role__name", "user__full_name")
    )

    # التقييمات الحالية لهذا العام
    existing_evals = {
        (e.employee_id, e.period): e
        for e in EmployeeEvaluation.objects.filter(
            school=school, academic_year=year
        ).select_related("evaluator")
    }

    # «مبذور» = قالبٌ هو استمارةُ دوره، كما يقرؤه `_get_axes_for_employee`.
    seeded_roles = {
        t.role_name
        for t in RoleEvaluationTemplate.objects.filter(
            school=school, academic_year=year, is_active=True
        ).prefetch_related("axes")
        if t.matches_ministry_form()
    }

    staff_list = []
    for m in memberships:
        s1_eval = existing_evals.get((m.user_id, "S1"))
        s2_eval = existing_evals.get((m.user_id, "S2"))
        staff_list.append(
            {
                "user": m.user,
                "role": m.role,
                "role_display": m.role.get_name_display(),
                "s1": s1_eval,
                "s2": s2_eval,
                # المادة 16: «يضع الرئيس المباشر» — فلا زرَّ لتقييم المقيِّم نفسه.
                "is_self": viewer is not None and m.user_id == viewer.pk,
                "s2_blocked": _s2_blocked_reason(m.role.name, seeded_roles),
            }
        )
    return staff_list


@login_required
@capability_required("quality.evaluations")
def evaluation_dashboard(request):
    """لوحة تحكم تقييم الموظفين — مع قائمة الموظفين"""
    if not _require_evaluator(request):
        return HttpResponse("غير مسموح — للمدير ونائبيه فقط", status=403)

    school = request.user.get_school()
    year = request.GET.get("year") or _default_year(request)

    cycles = EvaluationCycle.objects.filter(school=school, academic_year=year)
    cycle_stats = []
    for c in cycles:
        rate = c.completion_rate
        # العتبةُ كما كانت في القالب: 100 أخضر، و50 فأكثر كهرمانيّ، وما دونها أحمر.
        tone = "success" if rate == 100 else "warning" if rate >= 50 else "danger"
        cycle_stats.append({"cycle": c, "completion_rate": rate, "tone": tone})

    recent_evals = list(
        EmployeeEvaluation.objects.filter(school=school, academic_year=year)
        .select_related("employee", "evaluator")
        .order_by("-created_at")[:20]
    )
    for ev in recent_evals:
        ev.status_tone = evaluation_status_tone(ev.status)
        ev.score_tone = evaluation_rating_tone(ev.rating)

    annual = annual_rating_summary(school, year)

    staff_list = _get_evaluable_staff(school, year, viewer=request.user)
    for row in staff_list:
        row["s1_tone"] = evaluation_status_tone(row["s1"].status) if row["s1"] else ""
        row["s2_tone"] = evaluation_status_tone(row["s2"].status) if row["s2"] else ""

    return render(
        request,
        "quality/evaluation_dashboard.html",
        {
            "cycle_stats": cycle_stats,
            "recent_evals": recent_evals,
            "avg_score": annual.average,
            "rating_dist": annual.levels,
            "staff_list": staff_list,
            "year": year,
            "school": school,
        },
    )


def _save_evaluation(request, obj, axes):
    """معالجة POST: الحفظُ والتحقّقُ وقيدُ الجزاء في `evaluation_services.save_evaluation`."""
    save_evaluation(evaluation=obj, evaluator=request.user, axes=axes, data=request.POST)
    AuditLog.log(
        user=request.user,
        action="update",
        model_name="other",
        object_id=obj.pk,
        object_repr=str(obj),
        request=request,
        changes={"total_score": obj.total_score, "rating": obj.rating},
    )


def _axes_for_evaluation(school, employee, year, existing):
    """
    محاورُ النموذج. تقييمٌ عليه ما يُفقَد (درجاتٌ أو حالةٌ فوق المسودّة) يُعرض على المحاور
    التي حُفظ بها: قالبُه إن كان مربوطاً، وإلّا الافتراضيّةُ الأربعة — ولا يُنقل إلى قالب
    دوره الحاليّ. كان مجرّدُ فتحه بعد بذر القوالب (أو بعد تغيّر دور الموظّف) يربطه بالقالب
    الجديد ويعرض محاوره صفراً، ثمّ يمحو الحفظُ التالي درجاتِه من المجموع.

    والعبرةُ بموضع الدرجات لا بالربط: صفٌّ ربطه الـGET القديمُ بقالبٍ ودرجاتُه في المحاور
    الأربعة (بلا `EvaluationScore`) يُعرض عليها هي، ويُفكّ ربطُه عند الحفظ — فالتقريرُ
    السنويّ عليها يُرفض حينئذٍ بدل أن يُعتمد بمجموعٍ من غير الاستمارة.
    """
    if existing is not None and existing.has_saved_content():
        if (
            existing.template is not None
            and existing.template.axes.exists()
            and not existing.has_default_axis_scores()
        ):
            return [(a.key, a.label, a.weight) for a in existing.template.axes.all()], (
                existing.template
            )
        return _DEFAULT_AXES, None
    return _get_axes_for_employee(school, employee, year)


@login_required
@capability_required("quality.evaluations")
def create_evaluation(request, employee_id):
    """إنشاء أو تعديل تقييم موظف — مع ربط قالب الدور"""
    if not _require_evaluator(request):
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    employee = get_object_or_404(CustomUser, id=employee_id)
    year = request.GET.get("year") or _default_year(request)
    period = request.GET.get("period", EmployeeEvaluation.MINISTRY_PERIOD)
    # العامُ يُمرَّر إلى فحص وقائع المواد 17–19 وإلى القالب — فعامٌ بصيغةٍ أخرى
    # («2026/2027») كان يُفلت من الفحص ويُكتب تحت عامٍ لا تقرؤه اللوحة.
    if not is_academic_year(year) or period not in dict(EmployeeEvaluation.PERIODS):
        return HttpResponse("العامُ أو الفترةُ غيرُ صالحين", status=400)

    if not Membership.objects.filter(school=school, user=employee, is_active=True).exists():
        return HttpResponse("الموظف ليس في مدرستك", status=403)
    # «وتتولى لجنة شؤون المدارس، تقييم أداء مديري المدارس سنوياً» (02_staff_affairs.md:199)
    # — فلا تقييمَ للمدير من داخل المدرسة، وليس بين الاستمارات السبع استمارتُه.
    if is_school_principal(school, employee):
        return HttpResponse(PRINCIPAL_NOT_EVALUATED, status=403)
    if employee.pk == request.user.pk:
        return HttpResponse(SELF_EVALUATION, status=403)

    existing = (
        EmployeeEvaluation.objects.filter(
            school=school, employee=employee, academic_year=year, period=period
        )
        .select_related("template")
        .first()
    )
    axes, template = _axes_for_evaluation(school, employee, year, existing)
    has_content = existing is not None and existing.has_saved_content()

    # التقريرُ السنويّ «وفقاً للنماذج المعتمدة من الوزير» (المادة 15، 02_staff_affairs.md:199).
    # فدورٌ لا استمارةَ له لا يُولَّد له تقريرٌ على المحاور الأربعة الافتراضيّة (وليست في أيّ
    # استمارة) حتى يُحسم أمرُه (ADR-0002 §6.4، §6.6 بند 12). ويبقى المحفوظُ قبل ذلك معروضاً.
    if period == EmployeeEvaluation.MINISTRY_PERIOD and template is None and not has_content:
        role_name = _get_employee_role(school, employee)
        if role_name in forms_by_role():
            reason = "لم تُبذر استمارتُه لهذا العام — seed_quality_templates --apply"
        else:
            reason = "المصدرُ الوزاريّ لا يسمّي استمارةً لدوره — القرارُ للمالك (ADR-0002 §6.6)"
        return HttpResponse(
            f"لا يُفتح التقريرُ السنويّ لـ{employee.full_name} ({role_name}): {reason}.",
            status=409,
        )

    if request.method == "POST":
        try:
            # الإنشاءُ وربطُ القالب والحفظُ معاملةٌ واحدة: الطلبُ المرفوض لا يترك مسودّةً.
            with transaction.atomic():
                obj = existing or EmployeeEvaluation(
                    school=school,
                    employee=employee,
                    academic_year=year,
                    period=period,
                    evaluator=request.user,
                )
                if obj.template_id != (template.pk if template else None):
                    obj.template = template
                    if not obj._state.adding:
                        obj.save(update_fields=["template"])
                if obj._state.adding:
                    obj.save()
                _save_evaluation(request, obj, axes)
        except EvaluationRejectedError as exc:
            messages.error(request, str(exc))
            return redirect(request.get_full_path())
        if obj.status == "submitted":
            messages.success(request, f"تم تقديم تقييم {employee.full_name} بنجاح.")
        else:
            messages.info(request, "تم حفظ المسودة.")
        return redirect("evaluation_dashboard")

    # الـGET لا يكتب شيئاً: تقييمٌ لم يُحفظ بعدُ يُعرض من نسخةٍ غير محفوظة.
    obj = existing or EmployeeEvaluation(
        school=school, employee=employee, academic_year=year, period=period, template=template
    )

    # تقييمات المقيّمين المتعددين (إن وُجدت)
    scores = list(obj.scores.select_related("evaluator").all()) if existing else []

    # قيمةُ كلّ محور — كانت سلسلةَ `{% if %}` بأربعة فروعٍ مكرّرةً مرّتين في القالب.
    # ومحورُ قالب الدور لا حقلَ له في النموذج: قيمتُه من درجات هذا المقيِّم.
    # قيمُ الواضع لا الفاتح: المديرُ الذي يفتح التقريرَ ليعتمده كان يرى محاورَه أصفاراً.
    values = axis_values(obj, obj.evaluator, axes) if existing else {k: 0 for k, _l, _m in axes}
    axis_rows = [(key, label, weight, values[key]) for key, label, weight in axes]
    role_name = _get_employee_role(school, employee)
    subtitle_parts = [employee.full_name, role_name, obj.get_period_display(), year]

    return render(
        request,
        "quality/evaluation_form.html",
        {
            "obj": obj,
            "axis_rows": axis_rows,
            "form_subtitle": " · ".join(p for p in subtitle_parts if p),
            "axes_meta": (
                f"قالب: {template.role_name} ({template.total_weight} درجة)" if template else ""
            ),
            "score_tone": evaluation_rating_tone(obj.rating),
            "employee": employee,
            "year": year,
            "period": period,
            "axes": axes,
            "template": template,
            "scores": scores,
            "role_display": role_name,
            # المادة 16: واضعٌ واحد — فغيرُه يرى التقريرَ ولا يحفظ عليه.
            "is_editable": obj.status in ("draft", "submitted")
            and (not has_content or obj.evaluator_id == request.user.pk)
            and not (period == EmployeeEvaluation.MINISTRY_PERIOD and template is None),
            "can_approve": bool(existing)
            and obj.status == "submitted"
            and request.user.get_role() == "principal",
            "can_record_receipt": bool(existing)
            and obj.status == "approved"
            and obj.acknowledged_at is None
            and obj.received_on is None
            and request.user.get_role() == "principal",
        },
    )


@login_required
@capability_required("quality.evaluations")
@require_POST
def approve_evaluation(request, eval_id):
    """اعتمادُ مدير المدرسة للتقرير المُقدَّم — المادة 16 («ويعتمد من مدير المدرسة»)."""
    school = request.user.get_school()
    obj = get_object_or_404(EmployeeEvaluation, id=eval_id, school=school)
    try:
        approve_evaluation_service(evaluation=obj, approver=request.user)
    except EvaluationRejectedError as exc:
        messages.error(request, str(exc))
    else:
        AuditLog.log(
            user=request.user,
            action="update",
            model_name="other",
            object_id=obj.pk,
            object_repr=str(obj),
            request=request,
            changes={"status": "approved"},
        )
        messages.success(request, f"اعتُمد تقييم {obj.employee.full_name}.")
    return redirect(
        reverse("create_evaluation", kwargs={"employee_id": obj.employee_id})
        + f"?year={obj.academic_year}&period={obj.period}"
    )


@login_required
@capability_required("quality.evaluations")
@require_POST
def record_evaluation_receipt(request, eval_id):
    """
    المديرُ يدوّن تاريخ استلام الموظّف حين يرفض التوقيع — «استمارة تقييم المعلم والدليل
    التفسيري.pdf» ص2: «يرجى تدوين التاريخ في حالة رفض الموظف التوقيع».
    """
    school = request.user.get_school()
    obj = get_object_or_404(EmployeeEvaluation, id=eval_id, school=school)
    try:
        received_on = date.fromisoformat(request.POST.get("received_on", ""))
        record_receipt_on_refusal(evaluation=obj, recorder=request.user, received_on=received_on)
    except EvaluationRejectedError as exc:
        messages.error(request, str(exc))
    except ValueError:
        messages.error(request, "تاريخُ الاستلام غيرُ صالح.")
    else:
        AuditLog.log(
            user=request.user,
            action="update",
            model_name="other",
            object_id=obj.pk,
            object_repr=str(obj),
            request=request,
            changes={"received_on": received_on.isoformat()},
        )
        messages.success(request, "دُوِّن تاريخُ استلام الموظّف.")
    return redirect(
        reverse("create_evaluation", kwargs={"employee_id": obj.employee_id})
        + f"?year={obj.academic_year}&period={obj.period}"
    )


@login_required
def acknowledge_evaluation(request, eval_id):
    """الموظف يُقرّ باستلام تقييمه"""
    school = request.user.get_school()
    obj = get_object_or_404(EmployeeEvaluation, id=eval_id, employee=request.user, school=school)
    if obj.status != "approved":
        return HttpResponse("التقييم لم يُعتمد بعد", status=400)
    if request.method == "POST":
        obj.employee_comment = request.POST.get("comment", "")
        obj.acknowledge()
        messages.success(request, "تم تأكيد استلام التقييم.")
    return redirect("my_evaluations")


@login_required
def my_evaluations(request):
    """الموظف يرى تقييماته"""
    school = request.user.get_school()
    # «يعلن الموظف بنسخه من تقرير تقييم الأداء بمجرد اعتماده» (ملاحظةُ الاستمارات الخمس،
    # 06_attendance_performance_review.md:97؛ والمادة 20). فالمسودّةُ والمُقدَّم لا يُعرضان —
    # وكانت مسودّاتُ الصفر تظهر للموظّف «ضعيف (أقل من 50)».
    evals = list(
        EmployeeEvaluation.objects.filter(
            employee=request.user, school=school, status__in=["approved", "acknowledged"]
        )
        .select_related("evaluator", "template")
        .order_by("-created_at")
    )
    for ev in evals:
        ev.card_title = f"{ev.get_period_display()} — {ev.academic_year}"
        ev.score_tone = evaluation_rating_tone(ev.rating)
    return render(
        request,
        "quality/my_evaluations.html",
        {"evals": evals, "school": school},
    )
