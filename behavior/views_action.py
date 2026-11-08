"""شاشاتُ إجراء المخالفة المقترح: تجهيزُ المشرف واعتمادُ المنسّق وإحالاتُ الاختصاصيّين (W-20261108-007)."""

from uuid import UUID

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.capabilities import capability_required
from wings.scope import student_scope_for

from .action_services import FOLLOW_UPS, approve_action, approver_may_approve, prepare_action
from .selectors import pending_actions, specialist_referrals

_TEMPLATE = "behavior/action_queue.html"


@login_required
@capability_required("behavior.approve_action")
def action_queue(request: HttpRequest) -> HttpResponse:
    """المنسّقُ (أو النائبُ لما سجّله المنسّق) يتابع ويعتمد — لا يرى إلّا ما يحقّ له اعتمادُه."""
    items = [i for i in pending_actions(request.school) if approver_may_approve(request.user, i)]
    return render(request, _TEMPLATE, {"mode": "approve", "items": items, "follow_ups": FOLLOW_UPS})


@login_required
@capability_required("behavior.approve_action")
@require_POST
def action_approve(request: HttpRequest, infraction_id: UUID) -> HttpResponse:
    item = get_object_or_404(pending_actions(request.school), pk=infraction_id)
    try:
        approve_action(item, request.user, request.POST.get("follow_up", ""), request)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "اعتُمد الإجراء وسُجّل في سجلّ التدقيق.")
    return redirect("behavior:action_queue")


@login_required
@capability_required("behavior.prepare_action")
def action_prepare_list(request: HttpRequest) -> HttpResponse:
    """مشرفُ الجناح: مخالفاتُ طلبة جناحه التي اقتُرح لها إجراءٌ ليجهّز تعهّده أو إحالته."""
    items = pending_actions(request.school, student_scope_for(request))
    return render(request, _TEMPLATE, {"mode": "prepare", "items": items})


@login_required
@capability_required("behavior.prepare_action")
@require_POST
def action_prepare(request: HttpRequest, infraction_id: UUID) -> HttpResponse:
    """طالبٌ خارج الجناح 404 — كسائر شاشات المشرف؛ ولا استدعاءَ لوليّ الأمر هنا."""
    scope = student_scope_for(request)
    item = get_object_or_404(pending_actions(request.school, scope), pk=infraction_id)
    try:
        prepare_action(item, request.user, request.POST.get("kind", ""), request)
    except (ValueError, PermissionDenied) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "جُهّز الإجراء ويُرفع للمنسّق للاعتماد.")
    return redirect("behavior:action_prepare_list")


@login_required
@capability_required("behavior.specialist_referrals")
def referral_list(request: HttpRequest) -> HttpResponse:
    """الاختصاصيّان: إحالاتٌ بلغت عتبةَ السياسة لدراسة الحالة — للاطّلاع لا للاعتماد."""
    return render(
        request, _TEMPLATE, {"mode": "referrals", "items": specialist_referrals(request.school)}
    )
