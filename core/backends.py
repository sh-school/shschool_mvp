"""
core/backends.py — بابُ المصادقة بمعرّفٍ واحدٍ يُحَلّ
═══════════════════════════════════════════════════
حقلُ الدخول واحد، وما يُكتب فيه قد يكون رقماً وظيفيّاً (الكادر) أو رقماً
شخصيّاً (الطلبة وأولياء الأمور). والحلُّ في `core.auth_identity` وحدَه —
فالبابُ وaxes والعدّادُ يرون المستخدمَ نفسَه لا نصَّين مختلفين.
"""

from typing import Any

from django.contrib.auth.backends import ModelBackend

from core.auth_identity import resolve_user
from core.preview_accounts import blocked_outside_preview, report_blocked


class HMACAuthBackend(ModelBackend):
    """يُصادق بمعرّفٍ واحدٍ: الرقمُ الوظيفيُّ أوّلاً ثمّ الرقمُ الشخصيّ.

    و`national_id` يبقى مقبولاً وسيطاً لأنّه `USERNAME_FIELD` — تُمرّره أدواتُ
    Django نفسُها (`createsuperuser`، لوحةُ الإدارة).

    **مصيدةُ حسابات المعاينة** (W-20261003-023، حكمُ 0105 ب): حسابٌ موسومٌ (`core.preview_accounts`) خارج إعداد المعاينة لا يُصادَق
    (`user_can_authenticate`) ولا تبقى جلستُه (`get_user` يردّ `None` فتسقط الجلسةُ في الطلب التالي) — في مسار المصادقة نفسِه لا
    في صفحة الدخول وحدَها، وبحدثِ منعٍ يُنذَر منه.
    """

    def user_can_authenticate(self, user: Any) -> bool:
        if blocked_outside_preview(user):
            report_blocked(user, "authenticate")
            return False
        return super().user_can_authenticate(user)

    def get_user(self, user_id: Any) -> Any:
        user = super().get_user(user_id)
        if user is not None and blocked_outside_preview(user):
            report_blocked(user, "session")
            return None
        return user

    def authenticate(self, request, identifier=None, national_id=None, password=None, **kwargs):
        raw = identifier or national_id or kwargs.get("username")
        if not raw or not password:
            return None

        user = resolve_user(raw, request)
        if user is None:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
