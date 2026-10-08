"""نقطةُ الاستطلاع الحيّ للوحة مشرف الجناح وبديله (W-20261008-00x، D-249م القسم 9.3).

لا معاملَ في الطلب إطلاقاً: الجناحُ من `wings_of(user)` فلا مدخلَ لتزوير معرّف جناح. بديلٌ انتهى تكليفُه (أو دورٌ لا يحمل جناحاً) ← 403 فيتوقّف العميلُ ولا
يعيد المحاولة. `Cache-Control: no-store` و`Vary: Cookie`. والمخزَّنُ في الذاكرة المشتركة هو ملخّصُ المدرسة كلِّها (أعدادٌ بلا أسماء)، ويُقتطع لكلّ مستخدم بعد القراءة.
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET
from django.views.decorators.vary import vary_on_cookie

from core.capabilities import capability_required
from wings.supervisor_day import supervisor_day_payload


@login_required
@capability_required("dashboard.open")
@require_GET
@vary_on_cookie
def supervisor_live(request):
    payload = supervisor_day_payload(request.user, request.school, timezone.localdate())
    if payload is None:
        return JsonResponse({"error": "forbidden"}, status=403)
    response = JsonResponse(payload)
    response["Cache-Control"] = "no-store"
    return response
