"""شاشةُ إجراءات المخالفات المقترحة واعتمادِها (W-20261112-003).

القراءةُ في `proposed_action_selectors` والكتابةُ والتدقيقُ في `proposed_action_services`؛
والقرارُ لمن: المنسّقُ يعتمد (والنائبُ إن سجّل المنسّقُ بنفسه)، ومشرفُ الجناح يجهّز لجناحه، والاختصاصيّان يقرآن إحالاتِهما.
"""

from collections.abc import Callable
from uuid import UUID

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from behavior import proposed_action as pa
from behavior import proposed_action_services as services
from behavior.models import BehaviorInfraction
from behavior.proposed_action_selectors import queues_for
from behavior.selectors import school_infraction_or_404
from core.capabilities import capability_required
from core.permissions import forbidden_page
from wings.scope import student_scope_for


@login_required
@capability_required("behavior.proposed_actions")
def proposed_actions(request: HttpRequest) -> HttpResponse:
    """قوائمُ الإجراءات بحسب دور صاحب الشاشة: اعتمادٌ ومتابعةٌ للمنسّق، وتجهيزٌ للمشرف، وإحالاتٌ للاختصاصيَّين."""
    role = request.user.get_role()
    queues = queues_for(request.user, request.school, student_scope_for(request))
    return render(
        request,
        "behavior/proposed_actions.html",
        {
            "queues": queues,
            "is_approver": role in pa.APPROVER_ROLES,
            "is_specialist": role in pa.SPECIALIST_ROLES,
            "can_prepare": role == "admin_supervisor",
            "action_choices": pa.APPROVABLE_ACTIONS,
            "prepare_choices": BehaviorInfraction.PREPARED_KINDS,
            "followup_choices": BehaviorInfraction.FOLLOWUP_CHOICES,
        },
    )


def _apply(
    request: HttpRequest, infraction_id: UUID, write: Callable[..., None], **extra: str
) -> HttpResponse:
    """يطبّق كتابةً على مخالفةٍ من مدرسة الطلب ويعود إلى القائمة برسالة النتيجة."""
    infraction = school_infraction_or_404(request.school, infraction_id)
    try:
        write(infraction=infraction, user=request.user, request=request, **extra)
    except PermissionDenied as exc:
        return forbidden_page(request, str(exc))
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "تم الحفظ.")
    return redirect("behavior:proposed_actions")


@login_required
@capability_required("behavior.approve_action")
@require_POST
def approve_action(request: HttpRequest, infraction_id: UUID) -> HttpResponse:
    """اعتمادُ الإجراء المختار — المنسّقُ لما لم يسجّله، والنائبُ لما سجّله منسّق."""
    return _apply(
        request,
        infraction_id,
        services.approve_action,
        action=request.POST.get("action", ""),
    )


@login_required
@capability_required("behavior.approve_action")
@require_POST
def followup_action(request: HttpRequest, infraction_id: UUID) -> HttpResponse:
    """متابعةُ تنفيذ إجراءٍ معتمد: تمّ، لم يتمّ، جزئيًّا."""
    return _apply(
        request, infraction_id, services.record_followup, result=request.POST.get("result", "")
    )


@login_required
@capability_required("behavior.prepare_action")
@require_POST
def prepare_action(request: HttpRequest, infraction_id: UUID) -> HttpResponse:
    """مشرفُ الجناح يجهّز تعهّداً خطّيّاً أو إحالةً لطالبٍ من جناحه وحدَه؛ وغيرُه 404."""
    infraction = school_infraction_or_404(request.school, infraction_id)
    student_scope_for(request).require_student(infraction.student_id)
    return _apply(
        request, infraction_id, services.prepare_action, kind=request.POST.get("kind", "")
    )
