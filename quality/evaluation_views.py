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
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.academic_calendar import academic_year_for, default_academic_year
from core.capabilities import capability_required
from core.models import AuditLog, CustomUser

from . import evaluation_selectors as selectors
from .appraisal_forms import forms_by_role
from .evaluation_services import (
    PRINCIPAL_NOT_EVALUATED,
    SELF_EVALUATION,
    TEMPLATE_OFF_FORM,
    EvaluationRejectedError,
    annual_rating_summary,
    axis_values,
    developer_trial_note,
    first_year_rejection,
    form_template_ok,
    grievance_stage,
    is_academic_year,
    is_school_principal,
    may_act_as_principal,
    placement_rejection,
    record_receipt_on_refusal,
    save_evaluation_form,
)
from .evaluation_services import approve_evaluation as approve_evaluation_service
from .models import EmployeeEvaluation
from .presentation import evaluation_rating_tone, evaluation_status_tone, grievance_stage_tone


#: يُقرأ وقت الطلب لا وقت الاستيراد — ثابتُ الوحدة يتجمّد عند إقلاع العملية.
def _default_year(request=None):
    return academic_year_for(request) if request is not None else default_academic_year()


def _require_evaluator(request):
    """فقط المدير والنائبان يقيّمون"""
    return request.user.is_admin() or request.user.get_role() in (
        "vice_admin",
        "vice_academic",
    )


@login_required
@capability_required("quality.evaluations")
def evaluation_dashboard(request):
    """لوحة تحكم تقييم الموظفين — مع قائمة الموظفين"""
    if not _require_evaluator(request):
        return HttpResponse("غير مسموح — للمدير ونائبيه فقط", status=403)

    school = request.school
    year = request.GET.get("year") or _default_year(request)

    cycle_stats = []
    for c in selectors.get_cycles(school, year):
        rate = c.completion_rate
        # العتبةُ كما كانت في القالب: 100 أخضر، و50 فأكثر كهرمانيّ، وما دونها أحمر.
        tone = "success" if rate == 100 else "warning" if rate >= 50 else "danger"
        cycle_stats.append({"cycle": c, "completion_rate": rate, "tone": tone})

    recent_evals = selectors.get_recent_evaluations(school, year)
    for ev in recent_evals:
        ev.status_tone = evaluation_status_tone(ev.status)
        ev.score_tone = evaluation_rating_tone(ev.rating)

    annual = annual_rating_summary(school, year)

    staff_list = selectors.get_evaluable_staff(school, year, viewer=request.user)
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
            "can_view_grievances": request.user.is_superuser
            or is_school_principal(school, request.user),
            "grievances_waiting": sum(
                1
                for g in selectors.get_grievances(school, year)
                if grievance_stage(g).code in ("filed", "decided")
            ),
        },
    )


def _audit_saved(request, obj):
    AuditLog.log(
        user=request.user,
        action="update",
        model_name="other",
        object_id=obj.pk,
        object_repr=str(obj),
        request=request,
        changes={"total_score": obj.total_score, "rating": obj.rating},
    )


def _annual_report_blocked(school, employee, template, has_content):
    """
    التقريرُ السنويّ «وفقاً للنماذج المعتمدة من الوزير» (المادة 15، 02_staff_affairs.md:199).
    فدورٌ لا استمارةَ له لا يُولَّد له تقريرٌ على المحاور الأربعة الافتراضيّة (وليست في أيّ
    استمارة) حتى يُحسم أمرُه (ADR-0002 §6.4، §6.6 بند 12). ويبقى المحفوظُ قبل ذلك معروضاً.
    """
    if template is not None or has_content:
        return None
    role_name = selectors.get_employee_role(school, employee)
    if role_name in forms_by_role():
        reason = "لم تُبذر استمارتُه لهذا العام — seed_quality_templates --apply"
    else:
        reason = "المصدرُ الوزاريّ لا يسمّي استمارةً لدوره — القرارُ للمالك (ADR-0002 §6.6)"
    return HttpResponse(
        f"لا يُفتح التقريرُ السنويّ لـ{employee.full_name} ({role_name}): {reason}.",
        status=409,
        content_type="text/plain; charset=utf-8",
    )


def _form_context(request, obj, *, existing, axes, template, employee, year, period, has_content):
    # ومحورُ قالب الدور لا حقلَ له في النموذج: قيمتُه من درجات هذا المقيِّم. وقيمُ الواضع لا
    # الفاتح: المديرُ الذي يفتح التقريرَ ليعتمده كان يرى محاورَه أصفاراً.
    values = axis_values(obj, obj.evaluator, axes) if existing else {k: 0 for k, _l, _m in axes}
    axis_rows = [(key, label, weight, values[key]) for key, label, weight in axes]
    role_name = selectors.get_employee_role(request.school, employee)
    subtitle_parts = [employee.full_name, role_name, obj.get_period_display(), year]
    # التقريرُ السنويّ على قالبٍ خرج عن الاستمارة لا يُحفظ ولا يُعتمد (المادة 15،
    # 02_staff_affairs.md:199) — فلا يُعرض زرٌّ يُفضي إلى رفض، ويُقال السببُ مرّةً.
    off_form = period == EmployeeEvaluation.MINISTRY_PERIOD and not form_template_ok(obj)
    if off_form and template is not None:
        messages.warning(request, TEMPLATE_OFF_FORM)
    is_principal = may_act_as_principal(request.school, request.user)
    return {
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
        # تقييمات المقيّمين المتعددين (إن وُجدت)
        "scores": selectors.get_scores(obj) if existing else [],
        "role_display": role_name,
        # المادة 16: واضعٌ واحد — فغيرُه يرى التقريرَ ولا يحفظ عليه.
        "is_editable": obj.status in ("draft", "submitted")
        and (not has_content or obj.evaluator_id == request.user.pk)
        and not off_form,
        # الاعتمادُ يرفض ما ليس درجاتِ الاستمارة (`approve_evaluation`)، فالزرُّ بشرطه نفسه.
        "can_approve": bool(existing)
        and obj.status == "submitted"
        and is_principal
        and (period != EmployeeEvaluation.MINISTRY_PERIOD or obj.has_form_scores()),
        "can_record_receipt": bool(existing)
        and obj.status == "approved"
        and obj.acknowledged_at is None
        and obj.received_on is None
        and is_principal,
    }


def _evaluation_target(request, employee_id):
    """(الموظّف، العام، الفترة، ردٌّ مرفوض) — الردُّ غيرُ فارغٍ إن لم يجز التقييمُ."""
    school = request.school
    employee = get_object_or_404(CustomUser, id=employee_id)
    year = request.GET.get("year") or _default_year(request)
    period = request.GET.get("period", EmployeeEvaluation.MINISTRY_PERIOD)
    # العامُ يُمرَّر إلى فحص وقائع المواد 17–19 وإلى القالب — فعامٌ بصيغةٍ أخرى
    # («2026/2027») كان يُفلت من الفحص ويُكتب تحت عامٍ لا تقرؤه اللوحة.
    if not is_academic_year(year) or period not in dict(EmployeeEvaluation.PERIODS):
        return employee, year, period, HttpResponse("العامُ أو الفترةُ غيرُ صالحين", status=400)
    if not selectors.is_active_member(school, employee):
        return employee, year, period, HttpResponse("الموظف ليس في مدرستك", status=403)
    # «وتتولى لجنة شؤون المدارس، تقييم أداء مديري المدارس سنوياً» (02_staff_affairs.md:199)
    # — فلا تقييمَ للمدير من داخل المدرسة، وليس بين الاستمارات السبع استمارتُه.
    if is_school_principal(school, employee):
        return employee, year, period, HttpResponse(PRINCIPAL_NOT_EVALUATED, status=403)
    if employee.pk == request.user.pk:
        return employee, year, period, HttpResponse(SELF_EVALUATION, status=403)
    reason = placement_rejection(school, request.user, employee)
    if reason is not None:
        return employee, year, period, HttpResponse(reason, status=403)
    if period == EmployeeEvaluation.MINISTRY_PERIOD:
        reason = first_year_rejection(employee, year)
        if reason is not None:
            return (
                employee,
                year,
                period,
                HttpResponse(reason, status=409, content_type="text/plain; charset=utf-8"),
            )
    return employee, year, period, None


@login_required
@capability_required("quality.evaluations")
def create_evaluation(request, employee_id):
    """إنشاء أو تعديل تقييم موظف — مع ربط قالب الدور"""
    if not _require_evaluator(request):
        return HttpResponse("غير مسموح", status=403)

    school = request.school
    employee, year, period, rejected = _evaluation_target(request, employee_id)
    if rejected is not None:
        return rejected

    existing = selectors.find_evaluation(school, employee, year, period)
    axes, template = selectors.axes_for_evaluation(school, employee, year, existing)
    has_content = existing is not None and existing.has_saved_content()

    if period == EmployeeEvaluation.MINISTRY_PERIOD:
        blocked = _annual_report_blocked(school, employee, template, has_content)
        if blocked is not None:
            return blocked

    if request.method == "POST":
        try:
            obj = save_evaluation_form(
                school=school,
                employee=employee,
                year=year,
                period=period,
                existing=existing,
                template=template,
                axes=axes,
                evaluator=request.user,
                data=request.POST,
            )
        except EvaluationRejectedError as exc:
            messages.error(request, str(exc))
            return redirect(request.get_full_path())
        _audit_saved(request, obj)
        if obj.status == "submitted":
            messages.success(request, f"تم تقديم تقييم {employee.full_name} بنجاح.")
        else:
            messages.info(request, "تم حفظ المسودة.")
        return redirect("evaluation_dashboard")

    # الـGET لا يكتب شيئاً: تقييمٌ لم يُحفظ بعدُ يُعرض من نسخةٍ غير محفوظة.
    obj = existing or EmployeeEvaluation(
        school=school, employee=employee, academic_year=year, period=period, template=template
    )
    context = _form_context(
        request,
        obj,
        existing=existing,
        axes=axes,
        template=template,
        employee=employee,
        year=year,
        period=period,
        has_content=has_content,
    )
    return render(request, "quality/evaluation_form.html", context)


@login_required
@capability_required("quality.evaluations")
@require_POST
def approve_evaluation(request, eval_id):
    """اعتمادُ مدير المدرسة للتقرير المُقدَّم — المادة 16 («ويعتمد من مدير المدرسة»)."""
    school = request.school
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
            changes={"status": "approved", **developer_trial_note(school, request.user)},
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
    school = request.school
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
            changes={
                "received_on": received_on.isoformat(),
                **developer_trial_note(school, request.user),
            },
        )
        messages.success(request, "دُوِّن تاريخُ استلام الموظّف.")
    return redirect(
        reverse("create_evaluation", kwargs={"employee_id": obj.employee_id})
        + f"?year={obj.academic_year}&period={obj.period}"
    )


@login_required
def acknowledge_evaluation(request, eval_id):
    """الموظف يُقرّ باستلام تقييمه"""
    school = request.school
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
    school = request.school
    # «يعلن الموظف بنسخه من تقرير تقييم الأداء بمجرد اعتماده» (ملاحظةُ الاستمارات الخمس،
    # 06_attendance_performance_review.md:97؛ والمادة 20). فالمسودّةُ والمُقدَّم لا يُعرضان —
    # وكانت مسودّاتُ الصفر تظهر للموظّف «ضعيف (أقل من 50)».
    evals = selectors.get_published_evaluations(school, request.user)
    for ev in evals:
        ev.card_title = f"{ev.get_period_display()} — {ev.academic_year}"
        ev.score_tone = evaluation_rating_tone(ev.rating)
        ev.grievance = grievance_stage(ev)
        ev.grievance_tone = grievance_stage_tone(ev.grievance.code)
        ev.grievance_outcome_label = ev.get_grievance_outcome_display()
    return render(
        request,
        "quality/my_evaluations.html",
        {"evals": evals, "school": school},
    )
