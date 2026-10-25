"""اختيارُ الموظّف دورَه العامل عند تعدّد عضويّاته النشطة (W-20261019-008، قرار المالك 2026-10-19).

الدورُ الحاكمُ الافتراضيّ يبقى بترتيبه (`role_rank` ثمّ الأقدم انضماماً) — لا يتغيّر دورُ أحدٍ تلقائيّاً.
ومن له أكثرُ من عضويّةٍ نشطةٍ يختار من «تبديل الدور»؛ فيُحفظ اختيارُه في الجلسة ويتقدّم على الترتيب
ما دام عضويّةً نشطةً له، وإلا رجع الحاكمُ الافتراضيّ. فلا يُقبل معرِّفُ عضويّةٍ لغيره ولا لغير نشطة.
"""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest
from django.http.response import HttpResponseBase

SESSION_KEY = "active_membership_id"
PREFERRED_ATTR = "_preferred_membership_id"


class ActiveRoleChoiceMiddleware:
    """ينقل اختيارَ الجلسة إلى المستخدم قبل أن يقرأ أيُّ وسيطٍ عضويّاتِه (RLS وغيرُه)."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponseBase]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            chosen = request.session.get(SESSION_KEY)
            if chosen:
                setattr(
                    user, PREFERRED_ATTR, str(chosen)
                )  # عبر الغلاف الكسول إلى كائن المستخدم نفسه
        return self.get_response(request)
