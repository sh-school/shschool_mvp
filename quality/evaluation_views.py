"""
quality/evaluation_views.py
Phase 6 — واجهات تقييم الموظفين
القرار الأميري 9/2016 + قانون تنظيم المدارس 9/2017
"""

from django.conf import settings

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from core.models import AuditLog, CustomUser, Membership

from .models import EmployeeEvaluation, EvaluationCycle

_DEFAULT_YEAR = settings.CURRENT_ACADEMIC_YEAR


def _require_evaluator(request):
    """فقط المدير والنائبان يقيّمون"""
    return request.user.is_admin() or request.user.get_role() in ("vice_admin", "vice_academic")


@login_required
def evaluation_dashboard(request):
    """لوحة تحكم تقييم الموظفين"""
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
        school=school, academic_year=year, status__in=["submitted", "approved", "acknowledged"]
    ).aggregate(avg=Avg("total_score"))["avg"]

    rating_dist = (
        EmployeeEvaluation.objects.filter(school=school, academic_year=year)
        .values("rating")
        .annotate(count=Count("id"))
    )

    return render(
        request,
        "quality/evaluation_dashboard.html",
        {
            "cycle_stats": cycle_stats,
            "recent_evals": recent_evals,
            "avg_score": round(avg, 1) if avg else None,
            "rating_dist": {r["rating"]: r["count"] for r in rating_dist},
            "year": year,
            "school": school,
        },
    )


def _save_evaluation(request, obj):
    """معالجة POST لحفظ التقييم — Clean Code: SRP"""
    obj.axis_professional = int(request.POST.get("axis_professional", 0))
    obj.axis_commitment = int(request.POST.get("axis_commitment", 0))
    obj.axis_teamwork = int(request.POST.get("axis_teamwork", 0))
    obj.axis_development = int(request.POST.get("axis_development", 0))
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
def create_evaluation(request, employee_id):
    """إنشاء أو تعديل تقييم موظف"""
    if not _require_evaluator(request):
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    employee = get_object_or_404(CustomUser, id=employee_id)
    year = request.GET.get("year", _DEFAULT_YEAR)
    period = request.GET.get("period", "S1")

    if not Membership.objects.filter(school=school, user=employee, is_active=True).exists():
        return HttpResponse("الموظف ليس في مدرستك", status=403)

    obj, _ = EmployeeEvaluation.objects.get_or_create(
        school=school,
        employee=employee,
        academic_year=year,
        period=period,
        defaults={"evaluator": request.user},
    )

    if request.method == "POST":
        _save_evaluation(request, obj)
        if obj.status == "submitted":
            messages.success(request, f"تم تقديم تقييم {employee.full_name} بنجاح.")
        else:
            messages.info(request, "تم حفظ المسودة.")
        return redirect("evaluation_dashboard")

    return render(
        request,
        "quality/evaluation_form.html",
        {"obj": obj, "employee": employee, "year": year, "period": period},
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
    evals = EmployeeEvaluation.objects.filter(employee=request.user, school=school).order_by(
        "-created_at"
    )
    return render(
        request,
        "quality/my_evaluations.html",
        {"evals": evals, "school": school},
    )
