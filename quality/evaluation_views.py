"""
quality/evaluation_views.py
Phase 6 — واجهات تقييم الموظفين
القرار الأميري 9/2016 + قانون تنظيم المدارس 9/2017

إصلاح: ربط RoleEvaluationTemplate + EvaluationScore + قائمة الموظفين
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from core.models import AuditLog, CustomUser, Membership
from core.permissions import role_required

from .models import (
    EmployeeEvaluation,
    EvaluationCycle,
    EvaluationScore,
    RoleEvaluationTemplate,
    _EVALUABLE_ROLES,
)

_DEFAULT_YEAR = settings.CURRENT_ACADEMIC_YEAR

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
    """الحصول على دور الموظف في المدرسة"""
    membership = Membership.objects.filter(
        school=school, user=employee, is_active=True
    ).select_related("role").first()
    return membership.role.name if membership else None


def _get_axes_for_employee(school, employee, year):
    """
    الحصول على محاور التقييم حسب دور الموظف.
    إذا وُجد قالب مخصص → محاور القالب.
    وإلا → المحاور الأربعة الافتراضية.
    """
    role_name = _get_employee_role(school, employee)
    if role_name:
        template = RoleEvaluationTemplate.objects.filter(
            school=school, role_name=role_name, academic_year=year, is_active=True
        ).prefetch_related("axes").first()
        if template and template.axes.exists():
            return (
                [(a.key, a.label, a.weight) for a in template.axes.all()],
                template,
            )
    return _DEFAULT_AXES, None


def _get_evaluable_staff(school, year):
    """قائمة الموظفين القابلين للتقييم مع حالة التقييم"""
    memberships = (
        Membership.objects.filter(
            school=school, is_active=True, role__name__in=_EVALUABLE_ROLES
        )
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

    staff_list = []
    for m in memberships:
        s1_eval = existing_evals.get((m.user_id, "S1"))
        s2_eval = existing_evals.get((m.user_id, "S2"))
        staff_list.append({
            "user": m.user,
            "role": m.role,
            "role_display": m.role.get_name_display(),
            "s1": s1_eval,
            "s2": s2_eval,
        })
    return staff_list


@login_required
@role_required({"principal", "vice_admin", "vice_academic"})
def evaluation_dashboard(request):
    """لوحة تحكم تقييم الموظفين — مع قائمة الموظفين"""
    if not _require_evaluator(request):
        return HttpResponse("غير مسموح — للمدير ونائبيه فقط", status=403)

    school = request.user.get_school()
    year = request.GET.get("year", _DEFAULT_YEAR)

    cycles = EvaluationCycle.objects.filter(school=school, academic_year=year)
    cycle_stats = [{"cycle": c, "completion_rate": c.completion_rate} for c in cycles]

    recent_evals = (
        EmployeeEvaluation.objects.filter(school=school, academic_year=year)
        .select_related("employee", "evaluator")
        .order_by("-created_at")[:20]
    )

    avg = EmployeeEvaluation.objects.filter(
        school=school,
        academic_year=year,
        status__in=["submitted", "approved", "acknowledged"],
    ).aggregate(avg=Avg("total_score"))["avg"]

    rating_dist = (
        EmployeeEvaluation.objects.filter(school=school, academic_year=year)
        .values("rating")
        .annotate(count=Count("id"))
    )

    staff_list = _get_evaluable_staff(school, year)

    return render(
        request,
        "quality/evaluation_dashboard.html",
        {
            "cycle_stats": cycle_stats,
            "recent_evals": recent_evals,
            "avg_score": round(avg, 1) if avg else None,
            "rating_dist": {r["rating"]: r["count"] for r in rating_dist},
            "staff_list": staff_list,
            "year": year,
            "school": school,
        },
    )


def _save_evaluation(request, obj, axes):
    """معالجة POST لحفظ التقييم — يدعم المحاور الافتراضية والمخصصة"""
    # المحاور الافتراضية الأربعة
    for field_name, _label, _max_val in _DEFAULT_AXES:
        val = int(request.POST.get(field_name, 0))
        setattr(obj, field_name, val)

    obj.strengths = request.POST.get("strengths", "")
    obj.improvements = request.POST.get("improvements", "")
    obj.goals_next = request.POST.get("goals_next", "")
    obj.status = request.POST.get("action", "draft")
    obj.evaluator = request.user
    obj.save()

    AuditLog.log(
        user=request.user,
        action="update",
        model_name="other",
        object_id=obj.pk,
        object_repr=str(obj),
        request=request,
        changes={"total_score": obj.total_score, "rating": obj.rating},
    )


@login_required
@role_required({"principal", "vice_admin", "vice_academic"})
def create_evaluation(request, employee_id):
    """إنشاء أو تعديل تقييم موظف — مع ربط قالب الدور"""
    if not _require_evaluator(request):
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    employee = get_object_or_404(CustomUser, id=employee_id)
    year = request.GET.get("year", _DEFAULT_YEAR)
    period = request.GET.get("period", "S1")

    if not Membership.objects.filter(
        school=school, user=employee, is_active=True
    ).exists():
        return HttpResponse("الموظف ليس في مدرستك", status=403)

    # الحصول على محاور التقييم حسب دور الموظف
    axes, template = _get_axes_for_employee(school, employee, year)

    obj, _ = EmployeeEvaluation.objects.get_or_create(
        school=school,
        employee=employee,
        academic_year=year,
        period=period,
        defaults={"evaluator": request.user, "template": template},
    )

    # تحديث القالب إذا لم يكن مربوطاً
    if template and not obj.template:
        obj.template = template
        obj.save(update_fields=["template"])

    if request.method == "POST":
        _save_evaluation(request, obj, axes)
        if obj.status == "submitted":
            messages.success(
                request, f"تم تقديم تقييم {employee.full_name} بنجاح."
            )
        else:
            messages.info(request, "تم حفظ المسودة.")
        return redirect("evaluation_dashboard")

    # تقييمات المقيّمين المتعددين (إن وُجدت)
    scores = obj.scores.select_related("evaluator").all()

    return render(
        request,
        "quality/evaluation_form.html",
        {
            "obj": obj,
            "employee": employee,
            "year": year,
            "period": period,
            "axes": axes,
            "template": template,
            "scores": scores,
            "role_display": _get_employee_role(school, employee),
        },
    )


@login_required
def acknowledge_evaluation(request, eval_id):
    """الموظف يُقرّ باستلام تقييمه"""
    school = request.user.get_school()
    obj = get_object_or_404(
        EmployeeEvaluation, id=eval_id, employee=request.user, school=school
    )
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
    evals = (
        EmployeeEvaluation.objects.filter(employee=request.user, school=school)
        .select_related("evaluator", "template")
        .order_by("-created_at")
    )
    return render(
        request,
        "quality/my_evaluations.html",
        {"evals": evals, "school": school},
    )
