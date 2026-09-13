"""
core/backends.py — بابُ المصادقة بمعرّفٍ واحدٍ يُحَلّ
═══════════════════════════════════════════════════
حقلُ الدخول واحد، وما يُكتب فيه قد يكون رقماً وظيفيّاً (الكادر) أو رقماً
شخصيّاً (الطلبة وأولياء الأمور). والحلُّ في `core.auth_identity` وحدَه —
فالبابُ وaxes والعدّادُ يرون المستخدمَ نفسَه لا نصَّين مختلفين.
"""

from django.contrib.auth.backends import ModelBackend

from core.auth_identity import resolve_user


class HMACAuthBackend(ModelBackend):
    """يُصادق بمعرّفٍ واحدٍ: الرقمُ الوظيفيُّ أوّلاً ثمّ الرقمُ الشخصيّ.

    و`national_id` يبقى مقبولاً وسيطاً لأنّه `USERNAME_FIELD` — تُمرّره أدواتُ
    Django نفسُها (`createsuperuser`، لوحةُ الإدارة).
    """

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
