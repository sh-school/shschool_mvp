"""نقطةُ استقبال القياس الميدانيّ — `POST /rum/collect/` (عقدُ `docs/rum_client_contract_2026-09.md`).

تردّ **204 دائماً** (حتى للرفض) بلا جسمٍ فلا يُستدلّ على شيء. معفاةٌ من CSRF (الـbeacon لا يحمل رأساً) وتمرّ بوسيط الدخول كسائر المنصّة
(مسجَّلٌ فقط)، لكنّها **لا تقرأ جلسةً ولا مستخدماً** ولا تُسجّل IP ولا وكيلاً ولا مرجعاً — تُمرَّر الحمولةُ المتحقَّقُ منها وحدَها إلى `rum.record`.
مطفأةٌ ما دام `RUM_ENDPOINT` فارغاً (الأصل): تردّ 204 ولا تجمع.
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from command_center import rum


@csrf_exempt
@require_POST
def collect(request: HttpRequest) -> HttpResponse:
    if getattr(settings, "RUM_ENDPOINT", ""):
        try:
            length = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = rum.MAX_BODY_BYTES + 1
        if length <= rum.MAX_BODY_BYTES:
            payload = rum.parse(request.body)
            if payload is not None:
                rum.record(payload)
    return HttpResponse(status=204)
