"""
core/backends.py — HMAC Authentication Backend
═══════════════════════════════════════════════
يبحث عن المستخدم عبر HMAC(national_id) بدل النص الصريح.
يدعم الانتقال التدريجي: يحاول HMAC أولاً ← fallback إلى national_id العادي.
"""

from django.contrib.auth.backends import ModelBackend

from core.models._crypto import hmac_field


class HMACAuthBackend(ModelBackend):
    """
    Backend يُصادق عبر HMAC hash للرقم الوطني.

    الترتيب:
    1. يحسب hmac_field(national_id)
    2. يبحث في national_id_hmac (سريع — مفهرس)
    3. إذا لم يجد: fallback إلى national_id العادي (backward compat)
    4. يتحقق من كلمة المرور
    """

    def authenticate(self, request, national_id=None, password=None, **kwargs):
        # Django يمرر username أحياناً بدل national_id
        username = national_id or kwargs.get("username")
        if not username or not password:
            return None

        from core.models import CustomUser

        user = None
        hashed = hmac_field(username)

        # محاولة 1: البحث بـ HMAC (الطريقة الجديدة المشفّرة)
        if hashed and hashed != username:
            try:
                user = CustomUser.objects.get(national_id_hmac=hashed)
            except CustomUser.DoesNotExist:
                pass

        # محاولة 2: fallback إلى national_id العادي (backward compat)
        if user is None:
            try:
                user = CustomUser.objects.get(national_id=username)
            except CustomUser.DoesNotExist:
                return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
