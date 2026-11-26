"""إرسالُ متابعة المشرف الإداريّ وإقرارُه بالاطّلاع (نموذج 19) — الكتابةُ في services."""

from __future__ import annotations

import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from core.capabilities import capability_required

from . import supervisor_followup_selectors as selectors
from . import supervisor_followup_services as services
from .supervisor_followup_views import MANAGE, VIEW


@login_required
@capability_required(MANAGE)
@require_POST
def supervisor_followup_send(request: HttpRequest, pk: uuid.UUID) -> HttpResponse:
    followup = selectors.get_follow_up(request.school, pk)  # type: ignore[attr-defined]
    try:
        sent = services.send_follow_up(followup, request)
    except services.FollowUpError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "أُرسلت المتابعة للمشرف." if sent else "سبق إرسال المتابعة.")
    return redirect("supervisor_followup_pdf_view", pk=followup.pk)


@login_required
@capability_required(VIEW)
@require_POST
def supervisor_followup_acknowledge(request: HttpRequest, pk: uuid.UUID) -> HttpResponse:
    """للمشرف صاحبِ المتابعة وحدَه — حتى من يملك الإدارةَ لا يُقرّ عنه."""
    school = request.school  # type: ignore[attr-defined]
    followup = selectors.readable_follow_up(school, request.user, pk)
    if followup.supervisor_id != request.user.pk:
        raise PermissionDenied
    comment = request.POST.get("supervisor_comment", "")
    try:
        done = services.acknowledge_follow_up(followup, comment, request)
    except services.FollowUpError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "سُجّل إقرارك بالاطّلاع." if done else "سبق تسجيل إقرارك.")
    return redirect("supervisor_followup_detail", pk=followup.pk)
