"""وسيطُ عدِّ أخطاء الخادم (5xx) — يغذّي بطاقةَ «أخطاء الخادم» في الإدارة (OWN-23).

يعدّ كلَّ استجابةٍ بحالة 500 فما فوق: استثناءٌ لم يُعالَج (يحوّله جانغو إلى 500 قبل أن يبلغ وسيطاً خارجيّاً)،
واستجابةٌ 5xx صريحةٌ من الشيفرة (`JsonResponse(..., status=500)`)، وانقطاعُ قاعدةِ البيانات (503 من `RLSMiddleware`).
ويُستثنى `/health/`: فحوصُ الصحّة تُرجع 503 عمداً حين يتوقّف العاملُ أو الـcache، وذلك يخصّ بطاقاتٍ أخرى.

صنفُ الاستثناء يأتي من إشارة `got_request_exception` (تُرسَل داخل `except` فيصحّ `sys.exc_info()`)
وتُعلَّق على الطلب، والوسيطُ يقرؤها عند الاستجابة. موضعُه في `MIDDLEWARE` مبكّرٌ عمداً كي يرى ما تنتجه الأوسطةُ الداخليّة.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

from asgiref.sync import iscoroutinefunction, markcoroutinefunction, sync_to_async
from django.core.signals import got_request_exception
from django.dispatch import receiver
from django.http import HttpRequest, HttpResponse

from core import error_counter

_EXC_ATTR = "_server_error_class"
_EXCLUDED_PREFIXES = ("/health/",)


@receiver(got_request_exception, dispatch_uid="core.middleware_errors.remember_exception")
def remember_exception(sender: Any, request: HttpRequest | None = None, **kwargs: Any) -> None:
    """يعلّق صنفَ الاستثناء على الطلب — لا يرفع أبداً: مُستقبِلُ الإشارة هذه لا يُلتقط خطؤه."""
    try:
        exc = sys.exc_info()[1]
        if request is not None and exc is not None:
            setattr(request, _EXC_ATTR, type(exc).__name__)
    except Exception:  # noqa: BLE001
        pass


def route_of(request: HttpRequest) -> str:
    """«GET students/<uuid:pk>/» — نمطُ المسار لا رابطُه الخام، فلا معرّفاتٍ ولا استعلاماتٍ شخصيّة."""
    match = getattr(request, "resolver_match", None)
    route = getattr(match, "route", "") or "بلا مسار"
    return f"{request.method} {route}"


def _count(request: HttpRequest, response: HttpResponse) -> None:
    if response.status_code < 500 or request.path.startswith(_EXCLUDED_PREFIXES):
        return
    error_counter.record(route_of(request), getattr(request, _EXC_ATTR, ""))


class ServerErrorCounterMiddleware:
    """يعدّ استجاباتِ 5xx — متزامنٌ وغيرُ متزامن، فلا يفرض قفزةَ خيطٍ على كلّ طلبٍ في ASGI."""

    sync_capable = True
    async_capable = True

    def __init__(self, get_response: Callable[..., Any]) -> None:
        self.get_response = get_response
        self._is_async = iscoroutinefunction(get_response)
        if self._is_async:
            markcoroutinefunction(self)

    def __call__(self, request: HttpRequest) -> Any:
        if self._is_async:
            return self._acall(request)
        response = self.get_response(request)
        _count(request, response)
        return response

    async def _acall(self, request: HttpRequest) -> HttpResponse:
        response: HttpResponse = await self.get_response(request)
        if response.status_code >= 500:  # الكتابةُ في الـcache متزامنة — لا تُكلَّف إلّا حين يلزم
            await sync_to_async(_count)(request, response)
        return response
