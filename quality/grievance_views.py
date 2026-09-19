"""
quality/grievance_views.py — تظلّمُ الموظّف من تقرير تقييم أدائه (المادة 20)

«يجوز للموظف أن يتظلم منه إلى لجنة موظفي المدارس خلال خمسة عشر يوماً من تاريخ علمه» —
`02_staff_affairs.md:211`. الموظّفُ يقدّم من `my_evaluations`، ومديرُ المدرسة يرى التظلّمات
ويدوّن قرارَ اللجنة واعتمادَ الوزير له. الحكمُ في `evaluation_services`.
"""

from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.academic_calendar import academic_year_for
from core.capabilities import capability_required
from core.models import AuditLog

from . import evaluation_selectors as selectors
from .evaluation_services import (
    EvaluationRejectedError,
    developer_trial_note,
    file_grievance,
    grievance_stage,
    is_academic_year,
    may_act_as_principal,
)
from .evaluation_services import record_grievance_decision as record_decision_service
from .models import EmployeeEvaluation
from .presentation import grievance_stage_tone


def _audit(request, obj, changes):
    AuditLog.log(
        user=request.user,
        action="update",
        model_name="other",
        object_id=obj.pk,
        object_repr=str(obj),
        request=request,
        changes=changes,
    )


def _date_or_none(value):
    return date.fromisoformat(value) if value else None


@login_required
@require_POST
def file_evaluation_grievance(request, eval_id):
    """الموظّفُ يتظلّم من تقريره المعتمَد — مرّةً واحدةً وبسببٍ مكتوب."""
    obj = get_object_or_404(
        EmployeeEvaluation, id=eval_id, employee=request.user, school=request.school
    )
    try:
        file_grievance(evaluation=obj, employee=request.user, reason=request.POST.get("reason", ""))
    except EvaluationRejectedError as exc:
        messages.error(request, str(exc))
    else:
        _audit(request, obj, {"grievance_submitted_on": obj.grievance_submitted_on.isoformat()})
        messages.success(request, "سُجِّل تظلّمُك وسيُحال إلى لجنة موظفي المدارس عبر مدير المدرسة.")
    return redirect("my_evaluations")


@login_required
@capability_required("quality.evaluations")
def evaluation_grievances(request):
    """
    مديرُ المدرسة: التظلّماتُ المقدَّمةُ ومرحلةُ كلٍّ منها، وتدوينُ قرار اللجنة. ومطوّرُ المنصّة
    (`is_superuser`) يرى ما يراه المديرُ **للعرض وحدَه** — التدوينُ للمدير (`record_grievance_decision`).
    """
    can_record = may_act_as_principal(request.school, request.user)
    if not (can_record or request.user.is_superuser):
        return HttpResponse("غير مسموح — لمدير المدرسة وحده", status=403)
    year = request.GET.get("year") or academic_year_for(request)
    if not is_academic_year(year):
        return HttpResponse("العامُ غيرُ صالح", status=400)
    rows = []
    for ev in selectors.get_grievances(request.school, year):
        stage = grievance_stage(ev)
        rows.append({"ev": ev, "stage": stage, "tone": grievance_stage_tone(stage.code)})
    waiting = [r for r in rows if r["stage"].code in ("filed", "decided")]
    return render(
        request,
        "quality/evaluation_grievances.html",
        {
            "rows": rows,
            "waiting": len(waiting),
            "year": year,
            "outcomes": EmployeeEvaluation.GRIEVANCE_OUTCOMES,
            "can_record": can_record,
        },
    )


@login_required
@capability_required("quality.evaluations")
@require_POST
def record_grievance_decision(request, eval_id):
    """مديرُ المدرسة يدوّن ما وصله من اللجنة: قرارَها وتاريخَ إخطار الموظّف، ثمّ اعتمادَ الوزير."""
    obj = get_object_or_404(EmployeeEvaluation, id=eval_id, school=request.school)
    try:
        record_decision_service(
            evaluation=obj,
            recorder=request.user,
            decided_on=_date_or_none(request.POST.get("decided_on")),
            outcome=request.POST.get("outcome", ""),
            approved_on=_date_or_none(request.POST.get("approved_on")),
        )
    except EvaluationRejectedError as exc:
        messages.error(request, str(exc))
    except ValueError:
        messages.error(request, "تاريخٌ غيرُ صالح.")
    else:
        _audit(
            request,
            obj,
            {
                "grievance_decided_on": str(obj.grievance_decided_on or ""),
                "grievance_outcome": obj.grievance_outcome,
                "grievance_decision_approved_on": str(obj.grievance_decision_approved_on or ""),
                **developer_trial_note(request.school, request.user),
            },
        )
        messages.success(request, "دُوِّن قرارُ اللجنة.")
    return redirect("evaluation_grievances")
