"""نقطةُ الاستطلاع الحيّ للوحة المدير (W-20261008-004، D-249م القسم 9): JSON خفيفٌ بلا أسماء فوق ذاكرةٍ مشتركة 20 ث.

لا معاملَ في الطلب إطلاقاً (لا مدخلَ لتزوير مدرسةٍ أو جناح)؛ والمدرسةُ والدورُ من جلسة المستخدم. دورٌ غيرُ المدير ← 403 فيتوقّف العميلُ
ولا يعيد المحاولة. `Cache-Control: no-store` و`Vary: Cookie` فلا تحفظه ذاكرةٌ وسيطة.
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET
from django.views.decorators.vary import vary_on_cookie

from core.capabilities import capability_required
from core.dashboard_selectors import DIRECTOR_ROLES
from operations.day_selectors import live_payload


@login_required
@capability_required("dashboard.open")
@require_GET
@vary_on_cookie
def director_live(request):
    user = request.user
    school = request.school
    if school is None or not (user.is_superuser or user.get_role() in DIRECTOR_ROLES):
        return JsonResponse({"error": "forbidden"}, status=403)
    response = JsonResponse(live_payload(school, timezone.localdate()))
    response["Cache-Control"] = "no-store"
    return response
