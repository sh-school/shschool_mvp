"""شاشاتُ اعتماد الإجراء المقترح — W-20261108-023. القراءةُ في `action_selectors` والكتابةُ في `action_services`."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.capabilities import capability_required

from . import action_selectors, action_services
from .forms import DISCIPLINARY_ACTION_CHOICES
from .models import BehaviorInfraction


def _page(
    request: HttpRequest, mode: str, title: str, rows: list[BehaviorInfraction]
) -> HttpResponse:
    return render(
        request,
        "behavior/action_queue.html",
        {
            "mode": mode,
            "title": title,
            "rows": rows,
            "action_choices": [c for c in DISCIPLINARY_ACTION_CHOICES if c[0]],
            "followup_choices": [c for c in BehaviorInfraction.FOLLOWUP_STATUSES if c[0]],
        },
    )


@login_required
@capability_required("behavior.approve_action")
def approval_queue(request: HttpRequest) -> HttpResponse:
    """اعتمادُ الإجراء المقترح — ثمّ متابعةُ ما اعتُمد."""
    rows = action_selectors.pending_for_approver(request.user, request.school)
    return _page(request, "approve", "اعتماد الإجراءات المقترحة", rows)


@login_required
@capability_required("behavior.approve_action")
def followup_queue(request: HttpRequest) -> HttpResponse:
    rows = action_selectors.approved_for_followup(request.user, request.school)
    return _page(request, "followup", "متابعة تنفيذ الإجراءات المعتمدة", rows)


@login_required
@capability_required("behavior.prepare_action")
def prepare_queue(request: HttpRequest) -> HttpResponse:
    rows = action_selectors.pending_for_supervisor(request.user, request.school)
    return _page(request, "prepare", "تجهيز التعهّد والإحالة لطلبة جناحك", rows)


@login_required
@capability_required("behavior.specialist_referrals")
def specialist_referrals(request: HttpRequest) -> HttpResponse:
    rows = action_selectors.specialist_referrals(request.school)
    return _page(request, "referrals", "الإحالات المعتمدة للأخصائيّين", rows)


def _apply(
    request: HttpRequest,
    infraction_id: Any,
    back: str,
    operation: Callable[[BehaviorInfraction], object],
    done: str,
) -> HttpResponse:
    """يطبّق عمليةً على مخالفةٍ من مدرسة الطلب؛ ورفضُ الحالة رسالةٌ، ورفضُ الصلاحية 403 من الخدمة."""
    infraction = get_object_or_404(
        BehaviorInfraction.objects.select_related("school", "reported_by"),
        pk=infraction_id,
        school=request.school,
    )
    try:
        operation(infraction)
    except action_services.ActionError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, done)
    return redirect(back)


@login_required
@capability_required("behavior.approve_action")
@require_POST
def approve_action(request: HttpRequest, infraction_id: Any) -> HttpResponse:
    chosen = request.POST.get("action_type", "")
    return _apply(
        request,
        infraction_id,
        "behavior:approval_queue",
        lambda row: action_services.approve(row, request.user, chosen),
        "اعتُمد الإجراء.",
    )


@login_required
@capability_required("behavior.approve_action")
@require_POST
def followup_action(request: HttpRequest, infraction_id: Any) -> HttpResponse:
    status = request.POST.get("status", "")
    return _apply(
        request,
        infraction_id,
        "behavior:followup_queue",
        lambda row: action_services.record_followup(row, request.user, status),
        "سُجّلت المتابعة.",
    )


@login_required
@capability_required("behavior.prepare_action")
@require_POST
def prepare_action(request: HttpRequest, infraction_id: Any) -> HttpResponse:
    kind = request.POST.get("kind", "")
    return _apply(
        request,
        infraction_id,
        "behavior:prepare_queue",
        lambda row: action_services.prepare(row, request.user, kind),
        "جُهّز للاعتماد.",
    )
