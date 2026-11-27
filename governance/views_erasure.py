"""شاشةُ توقيع طلبات محو بيانات الطالب (PDPPL م.18، U-11 المرحلة 2 ب).

العرضُ لا يقرّر شيئاً من قواعد التوقيع: يستدعي `ErasureService` ويعرض رفضَه وتعثّرَه
بالجمل الثابتة نفسِها التي يردّ بها الـAPI. ولا تقديمَ طلبٍ من هنا.
"""

import uuid
from collections.abc import Callable
from functools import wraps
from typing import Any

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseBase
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from core.permissions import _forbidden_response
from governance import erasure_selectors as selectors
from governance.erasure_messages import ERASURE_FAILURES, ERASURE_REFUSALS, ERASURE_RETRY_NOTE
from governance.erasure_service import ErasureFailedError, ErasureOfficerError, ErasureService

View = Callable[..., HttpResponseBase]


def _guard(allowed: Callable[[Any, Any], bool], roles: tuple[str, ...]) -> Callable[[View], View]:
    """حارسُ الشاشة: `allowed(user, school)` وإلّا 403 — و`_required_roles` يقرؤها حارسُ المسارات."""

    def decorator(view: View) -> View:
        @wraps(view)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
            if not allowed(request.user, getattr(request, "school", None)):
                return _forbidden_response(request, "ليست لديك صلاحية لهذه الشاشة.")
            return view(request, *args, **kwargs)

        wrapper._required_roles = roles  # type: ignore[attr-defined]
        return wrapper

    return decorator


signer_required = _guard(selectors.can_access, selectors.SIGNER_ROLES)
principal_required = _guard(selectors.is_principal, ("principal",))


@signer_required
@require_GET
def erasure_requests(request: HttpRequest) -> HttpResponse:
    context = selectors.screen_context(request.user, getattr(request, "school"))  # noqa: B009
    return render(request, "governance/erasure_requests.html", context)


@signer_required
@require_POST
def erasure_sign(request: HttpRequest, request_id: uuid.UUID) -> HttpResponse:
    """توقيعٌ بتأكيدٍ صريح — يُنفَّذ المحوُ عند اكتمال التوقيعين."""
    obj = selectors.school_request(getattr(request, "school"), request_id)  # noqa: B009
    if not request.POST.get("confirm"):
        messages.error(request, "لم يُسجَّل التوقيع: أكّد أوّلاً أنّك تعلم أنّ المحو لا رجعةَ فيه.")
        return redirect("erasure_requests")
    try:
        obj, summary = ErasureService.approve_and_execute(obj.pk, request.user)
    except tuple(ERASURE_REFUSALS) as refused:
        messages.error(request, ERASURE_REFUSALS[type(refused)][0])
    except ErasureFailedError as exc:
        # جملةٌ من الجدول الثابت لا نصُّ الاستثناء.
        detail = ERASURE_FAILURES.get(exc.code, ERASURE_FAILURES["erasure_error"])[1]
        messages.error(request, f"{detail} {ERASURE_RETRY_NOTE}")
    else:
        if summary is None:
            messages.success(request, "سُجّل توقيعك — يُنفَّذ المحو عند التوقيع الثاني.")
        else:
            messages.success(request, f"تم تنفيذ المحو بنجاح ({obj.anonymized_id}).")
    return redirect("erasure_requests")


@signer_required
@require_POST
def erasure_reject(request: HttpRequest, request_id: uuid.UUID) -> HttpResponse:
    obj = selectors.school_request(getattr(request, "school"), request_id)  # noqa: B009
    try:
        ErasureService.reject(obj.pk, request.user, request.POST.get("note", "").strip())
    except tuple(ERASURE_REFUSALS) as refused:
        messages.error(request, ERASURE_REFUSALS[type(refused)][0])
    else:
        messages.success(request, "رُفض طلبُ المحو وسُجّل السبب.")
    return redirect("erasure_requests")


@principal_required
@require_POST
def erasure_assign_officer(request: HttpRequest) -> HttpResponse:
    try:
        ErasureService.assign_officer(request.user, uuid.UUID(request.POST.get("user_id", "")))
    except (ValueError, ErasureOfficerError):
        messages.error(request, "المسؤولُ يُختار من كادر المدرسة النشط.")
    else:
        messages.success(request, "تم تعيين مسؤول حماية البيانات.")
    return redirect("erasure_requests")
