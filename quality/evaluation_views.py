"""
quality/evaluation_views.py
Phase 6 — واجهات تقييم الموظفين
القرار الأميري 9/2016 + قانون تنظيم المدارس 9/2017

إصلاح: ربط RoleEvaluationTemplate + EvaluationScore + قائمة الموظفين
"""

import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from core.academic_calendar import academic_year_for, default_academic_year
from core.capabilities import capability_required
from core.models import AuditLog, CustomUser, Membership

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


_YEAR_RE = re.compile(r"^\d{4}-\d{4}$")


def _year_from_request(request):
    """
    إصلاح ب.5 (منخفض): "year" من querystring يصل بلا تحقّق من صيغته —
    فقيمةٌ عشوائيةٌ (أو محاولة حقن) كانت تُمرَّر مباشرةً إلى فلاتر ORM.
    ترفض أي صيغةٍ لا تطابق "AAAA-AAAA" وتعود إلى العام الافتراضي.
    """
    year = request.GET.get("year")
    if year and _YEAR_RE.match(year):
        return year
    return _default_year(request)


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
    membership = (
        Membership.objects.filter(school=school, user=employee, is_active=True)
        .select_related("role")
        .first()
    )
    return membership.role.name if membership else None


def _get_axes_for_employee(school, employee, year):
    """
    الحصول على محاور التقييم حسب دور الموظف.
    إذا وُجد قالب مخصص → محاور القالب.
    وإلا → المحاور الأربعة الافتراضية.
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
        if template and template.axes.exists():
            return (
                [(a.key, a.label, a.weight) for a in template.axes.all()],
                template,
            )
    return _DEFAULT_AXES, None


def _get_evaluable_staff(school, year):
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
    year = _year_from_request(request)

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
    for row in staff_list:
        row["s1_tone"] = evaluation_status_tone(row["s1"].status) if row["s1"] else ""
        row["s2_tone"] = evaluation_status_tone(row["s2"].status) if row["s2"] else ""

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
@capability_required("quality.evaluations")
def create_evaluation(request, employee_id):
    """إنشاء أو تعديل تقييم موظف — مع ربط قالب الدور"""
    if not _require_evaluator(request):
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    employee = get_object_or_404(CustomUser, id=employee_id)
    year = _year_from_request(request)
    period = request.GET.get("period", "S1")

    if not Membership.objects.filter(school=school, user=employee, is_active=True).exists():
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

    # إصلاح ب.2 (مراجعة عدائيّة): كان مجرّدُ فتح تقييمٍ قائم (حتى المعتمَد)
    # بعد بذر قالبٍ جديد أو تغيّر دور الموظّف يربطه بالقالب الجديد فوراً،
    # فتُعرض محاوره صفراً (getattr على مفاتيح القالب الجديد لا وجود لها في
    # الدرجات المحفوظة). لا يُربط تقييمٌ له درجاتٌ محفوظة أو حالته غير
    # "مسودّة" بقالبٍ آخر تلقائياً — يبقى معروضاً على محاوره التي حُفظ بها.
    has_saved_axis_scores = any(
        getattr(obj, f, 0)
        for f in ("axis_professional", "axis_commitment", "axis_teamwork", "axis_development")
    )
    is_untouched_draft = (
        obj.status == "draft" and not has_saved_axis_scores and not obj.scores.exists()
    )
    if template and not obj.template and is_untouched_draft:
        obj.template = template
        obj.save(update_fields=["template"])
    elif obj.template:
        # تقييمٌ مربوطٌ بقالبٍ من قبل (وليس القالب المكتشَف الآن حديثاً) —
        # اعرض محاوره هو، لا محاور قالبٍ آخر قد يكون اكتُشف لدوره الحالي.
        axes = [(a.key, a.label, a.weight) for a in obj.template.axes.all()]
        template = obj.template
    elif has_saved_axis_scores or obj.scores.exists():
        # تقييمٌ قديمٌ بلا قالب لكنه محفوظٌ فعلياً على المحاور الافتراضية —
        # اعرضه عليها لا على قالبٍ جديد لا صلة لدرجاته به.
        axes, template = _DEFAULT_AXES, None

    if request.method == "POST":
        _save_evaluation(request, obj, axes)
        if obj.status == "submitted":
            messages.success(request, f"تم تقديم تقييم {employee.full_name} بنجاح.")
        else:
            messages.info(request, "تم حفظ المسودة.")
        return redirect("evaluation_dashboard")

    # تقييمات المقيّمين المتعددين (إن وُجدت)
    scores = obj.scores.select_related("evaluator").all()

    # قيمةُ كلّ محور — كانت سلسلةَ `{% if %}` بأربعة فروعٍ مكرّرةً مرّتين في القالب.
    # ومحورُ القالب المخصَّص الذي لا حقلَ له في النموذج يبدأ من صفر كما كان.
    axis_rows = [(key, label, weight, getattr(obj, key, 0) or 0) for key, label, weight in axes]
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
        },
    )


@login_required
@capability_required("quality.evaluations")
def approve_evaluation(request, eval_id):
    """
    إصلاح ب.1 — مسار الاعتماد الوحيد للتقييم، عوضاً عن تعديل `status` من
    شاشة الإدارة (التي كانت تعيد حساب المجموع من المحاور الافتراضية فتصفّر
    درجات القالب الوزاري). المديرُ وحده يعتمد (المادة 16: "يعتمد من مدير
    المدرسة")، والمجموعُ يُعاد حسابه من `EvaluationScore` لا من الأصفار.
    """
    school = request.user.get_school()
    obj = get_object_or_404(EmployeeEvaluation, id=eval_id, school=school)
    if not request.user.is_admin():
        return HttpResponse("الاعتمادُ لمدير المدرسة فقط (المادة 16)", status=403)
    if obj.status not in ("draft", "submitted"):
        return HttpResponse("لا يمكن اعتماد تقييمٍ بهذه الحالة", status=400)
    if request.method == "POST":
        obj.recalculate_from_scores()
        obj.status = "approved"
        obj.save(update_fields=["status"])
        AuditLog.log(
            user=request.user,
            action="update",
            model_name="other",
            object_id=obj.pk,
            object_repr=str(obj),
            request=request,
            changes={"status": "approved", "total_score": obj.total_score},
        )
        messages.success(request, f"تم اعتماد تقييم {obj.employee.full_name}.")
    return redirect("evaluation_dashboard")


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
    evals = list(
        EmployeeEvaluation.objects.filter(employee=request.user, school=school)
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
