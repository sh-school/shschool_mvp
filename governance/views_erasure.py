"""شاشةُ توقيع طلبات محو بيانات الطالب (U-11 المرحلة 2 ب، PDPPL م.18).

الكتابةُ والقواعدُ في `ErasureService`، والقراءةُ في `erasure_selectors`. لا تقديمَ طلبٍ من هنا.
"""

import uuid
from collections.abc import Callable
from functools import wraps
from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from core.capabilities import capability_required
from core.models import ErasureRequest
from governance.erasure_messages import (
    ERASURE_DONE_MESSAGE,
    ERASURE_REFUSAL_MESSAGES,
    ERASURE_RETRY_NOTE,
    ERASURE_SIGNED_MESSAGE,
    failure_for,
)
from governance.erasure_selectors import can_appoint, erasure_page, may_enter
from governance.erasure_service import (
    ErasureFailedError,
    ErasureNotSignerError,
    ErasureOfficerError,
    ErasureService,
)

CONFIRM_REQUIRED_MESSAGE = "لم يُسجَّل توقيعك: أقرّ أوّلاً بأنّ المحو لا رجعة فيه."
OFFICER_DONE_MESSAGE = "تم تعيين مسؤول حماية البيانات."
OFFICER_INVALID_MESSAGE = "المسؤولُ يُختار من كادر المدرسة النشط."


def _signers_only(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    """أضيقُ من القدرة: المطوّرُ وsuperuser لا يدخلان إلّا بصفةٍ من الثلاث (كما في الـAPI)."""

    @wraps(view)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not may_enter(request.user, getattr(request, "school", None)):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


def _school_request(request: HttpRequest, request_id: uuid.UUID) -> ErasureRequest:
    """طلبُ مدرسة المستخدم وحدَها — وغيرُه 404."""
    return get_object_or_404(ErasureRequest, pk=request_id, school=getattr(request, "school", None))


@login_required
@capability_required("governance.erasure_sign")  # type: ignore[misc]  # الحارسُ بلا أنواع في core
@_signers_only
@require_GET
def erasure_requests(request: HttpRequest) -> HttpResponse:
    context = erasure_page(request.user, getattr(request, "school", None))
    return render(request, "governance/erasure_requests.html", context)


@login_required
@capability_required("governance.erasure_sign")  # type: ignore[misc]  # الحارسُ بلا أنواع في core
@_signers_only
@require_POST
def erasure_sign(request: HttpRequest, request_id: uuid.UUID) -> HttpResponse:
    obj = _school_request(request, request_id)
    if request.POST.get("confirm") != "1":
        messages.error(request, CONFIRM_REQUIRED_MESSAGE)
        return redirect("governance:erasure_requests")
    try:
        _, summary = ErasureService.approve_and_execute(obj.pk, request.user)
    except tuple(ERASURE_REFUSAL_MESSAGES) as refused:
        messages.error(request, ERASURE_REFUSAL_MESSAGES[type(refused)])
    except ErasureFailedError as exc:
        messages.error(request, f"{failure_for(exc.code)[1]} {ERASURE_RETRY_NOTE}")
    else:
        messages.success(
            request, ERASURE_SIGNED_MESSAGE if summary is None else ERASURE_DONE_MESSAGE
        )
    return redirect("governance:erasure_requests")


@login_required
@capability_required("governance.erasure_sign")  # type: ignore[misc]  # الحارسُ بلا أنواع في core
@_signers_only
@require_POST
def erasure_reject(request: HttpRequest, request_id: uuid.UUID) -> HttpResponse:
    obj = _school_request(request, request_id)
    try:
        ErasureService.reject(obj.pk, request.user, request.POST.get("note", "").strip())
    except tuple(ERASURE_REFUSAL_MESSAGES) as refused:
        messages.error(request, ERASURE_REFUSAL_MESSAGES[type(refused)])
    else:
        messages.success(request, "رُفض طلب المحو.")
    return redirect("governance:erasure_requests")


@login_required
@capability_required("governance.appoint_dpo")  # type: ignore[misc]  # الحارسُ بلا أنواع في core
@require_POST
def erasure_appoint_officer(request: HttpRequest) -> HttpResponse:
    # بوّابةُ القدرة تمرّر المطوّرَ وsuperuser: يُردّان قبل قراءة المُدخل.
    if not can_appoint(request.user, getattr(request, "school", None)):
        raise PermissionDenied
    try:
        officer_id = uuid.UUID(request.POST.get("user_id", ""))
        ErasureService.assign_officer(request.user, officer_id)
    except (ValueError, ErasureOfficerError):
        messages.error(request, OFFICER_INVALID_MESSAGE)
    except ErasureNotSignerError as refused:
        raise PermissionDenied from refused
    else:
        messages.success(request, OFFICER_DONE_MESSAGE)
    return redirect("governance:erasure_requests")
