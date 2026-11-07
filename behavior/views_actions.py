"""شاشاتُ إجراء المخالفة: تجهيزُ المشرف، ومتابعةُ المنسّق واعتمادُه، وقائمةُ الاختصاصيَّين (W-20261108-005).

القراءةُ في `action_services` (قوائمُ بنطاق كلّ دور) والكتابةُ فيه (خدماتٌ تحرس القدرةَ والنطاقَ وفصلَ المهام).
لا إشعارَ لوليّ الأمر من هذه الشاشات: الاستدعاءُ والإشعارُ يدويّان بقدرة `behavior.summon_parent`.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.capabilities import capability_required

from . import action_services as flow
from .models import BehaviorInfraction


def _page(request: HttpRequest, mode: str, rows: QuerySet[BehaviorInfraction]) -> HttpResponse:
    return render(
        request,
        "behavior/actions.html",
        {
            "mode": mode,
            "rows": list(rows[:200]),
            "followup_statuses": BehaviorInfraction.FOLLOWUP_STATUSES,
            "prepared_kinds": BehaviorInfraction.PREPARED_KINDS,
        },
    )


@login_required
@capability_required("behavior.approve_action")
def approvals(request: HttpRequest) -> HttpResponse:
    """طابورُ المنسّق (أو النائب الإداريّ لما سجّله المنسّقُ): متابعةٌ واعتماد."""
    return _page(request, "approve", flow.approval_queue(request.user, request.school))


@login_required
@capability_required("behavior.prepare_action")
def prepare_list(request: HttpRequest) -> HttpResponse:
    """مخالفاتُ جناح المشرف لتجهيز تعهّدٍ خطّيّ أو إحالة."""
    return _page(request, "prepare", flow.prepare_queue(request.user, request.school))


@login_required
@capability_required("behavior.specialist_list")
def specialist_list(request: HttpRequest) -> HttpResponse:
    """الإحالاتُ عند عتبات السياسة — للدراسة فقط، بلا زرّ اعتماد."""
    return _page(request, "specialist", flow.specialist_queue(request.user, request.school))


def _run(
    request: HttpRequest,
    infraction_id: uuid.UUID,
    action: Callable[[BehaviorInfraction], object],
    done: str,
    back: str,
) -> HttpResponse:
    """يشغّل خدمةً على مخالفةِ مدرسةِ الطلب؛ ورفضُ القاعدة (ValueError) رسالةٌ لا خطأ خادم."""
    infraction = get_object_or_404(BehaviorInfraction, pk=infraction_id, school=request.school)
    try:
        action(infraction)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, done)
    return redirect(back)


@login_required
@require_POST
@capability_required("behavior.prepare_action")
def prepare(request: HttpRequest, infraction_id: uuid.UUID) -> HttpResponse:
    kind = request.POST.get("kind", "")
    return _run(
        request,
        infraction_id,
        lambda inf: flow.prepare_action(inf, request.user, kind),
        "جُهّز الإجراء.",
        "behavior:actions_prepare",
    )


@login_required
@require_POST
@capability_required("behavior.approve_action")
def followup(request: HttpRequest, infraction_id: uuid.UUID) -> HttpResponse:
    status = request.POST.get("status", "")
    return _run(
        request,
        infraction_id,
        lambda inf: flow.record_followup(inf, request.user, status),
        "سُجّلت المتابعة.",
        "behavior:actions",
    )


@login_required
@require_POST
@capability_required("behavior.approve_action")
def approve(request: HttpRequest, infraction_id: uuid.UUID) -> HttpResponse:
    text = request.POST.get("action_text", "")
    return _run(
        request,
        infraction_id,
        lambda inf: flow.approve_action(inf, request.user, text),
        "اعتُمد الإجراء.",
        "behavior:actions",
    )
