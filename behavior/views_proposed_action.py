"""شاشاتُ الإجراء المقترح من السلّم: اعتمادُ المنسّق، وتجهيزُ مشرف الجناح، وقائمةُ الأخصائيّين (W-20261108-027).

القراءةُ في `selectors.py` والكتابةُ في `proposed_action.py`. ولا إشعارَ آليّاً لوليّ الأمر من أيٍّ منها:
الاستدعاءُ يدويٌّ بقدرة `behavior.summon_parent`.
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from core.capabilities import capability_required
from wings.scope import student_scope_for

from . import proposed_action
from .models import BehaviorInfraction
from .selectors import pending_proposals, specialist_referrals


def _page(request: HttpRequest, mode: str, rows: Any) -> HttpResponse:
    context = {
        "mode": mode,
        "rows": rows,
        "follow_ups": BehaviorInfraction.FOLLOW_UP_CHOICES,
        "article": proposed_action.ARTICLE,
    }
    return render(request, "behavior/proposed_actions.html", context)


@login_required
@capability_required("behavior.approve_action")
@require_http_methods(["GET", "POST"])
def approve_proposals(request: HttpRequest) -> HttpResponse:
    """المنسّق (أو النائبُ إن كان المنسّقُ هو من سجّل) يتابع الإجراءَ المقترح ويعتمده."""
    rows = pending_proposals(request.school)
    if request.method == "POST":
        infraction = get_object_or_404(rows, pk=request.POST.get("infraction_id"))
        follow_up = request.POST.get("follow_up", "")
        try:
            proposed_action.approve(infraction, request.user, follow_up, request)
            messages.success(request, "اعتُمد الإجراء وسُجّلت المتابعة.")
        except ValueError as error:
            messages.error(request, str(error))
        return redirect("behavior:approve_proposals")
    return _page(request, "approve", rows)


@login_required
@capability_required("behavior.prepare_action")
@require_http_methods(["GET", "POST"])
def prepare_proposals(request: HttpRequest) -> HttpResponse:
    """مشرفُ الجناح يجهّز التعهّدَ الخطّيّ أو الإحالةَ لطلبة جناحه وحدَهم — لا استدعاءَ."""
    rows = pending_proposals(request.school, student_scope_for(request))
    if request.method == "POST":
        infraction = get_object_or_404(rows, pk=request.POST.get("infraction_id"))
        try:
            proposed_action.prepare(infraction, request.user, request.POST.get("kind", ""), request)
            messages.success(request, "جُهّز الإجراء بانتظار اعتماد المنسّق.")
        except ValueError as error:
            messages.error(request, str(error))
        return redirect("behavior:prepare_proposals")
    return _page(request, "prepare", rows)


@login_required
@capability_required("behavior.specialist_referrals")
def referral_list(request: HttpRequest) -> HttpResponse:
    """الأخصائيّان يريان الإحالاتِ عند عتبات السلّم (يُنقل رقمُ المادة وسطرُها) ليدرسا الحالة — بلا اعتماد."""
    return _page(request, "referrals", specialist_referrals(request.school))
