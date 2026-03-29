"""
operations/middleware.py — توليد الحصص التلقائي
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Middleware يضمن وجود حصص الأسبوع الحالي لكل مدرسة.
يعمل بشكل شفاف مع كل طلب — بدون أي تدخل يدوي.

الآلية:
  1. فحص cache سريع (≈0.2ms) — إذا تم التوليد اليوم → skip
  2. إذا أول طلب في اليوم → يولّد حصص الأسبوع كامل (أحد-خميس)
  3. يحفظ في cache لمدة 4 ساعات
  4. idempotent: bulk_create(ignore_conflicts=True)

الأداء:
  - Cache hit: ~0.2ms (لا overhead)
  - أول طلب في اليوم: ~10-15ms مرة واحدة فقط
  - بدون cache backend: يستخدم request attribute كـ fallback
"""

import logging

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

# المسارات المعفاة — لا تحتاج توليد حصص
_EXEMPT_PREFIXES = (
    "/static/",
    "/media/",
    "/favicon",
    "/__debug__",
    "/admin/jsi18n/",
    "/metrics",
    "/health",
)


class SessionAutoGenerateMiddleware:
    """
    يضمن وجود حصص الأسبوع الحالي تلقائياً.

    يعمل بعد SchoolPermissionMiddleware و CurrentUserMiddleware.
    يستخدم Django cache لتجنب التكرار.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        self._ensure_sessions(request)
        return self.get_response(request)

    def _ensure_sessions(self, request):
        """التحقق وتوليد الحصص إذا لزم الأمر."""
        # ── فحص سريع: هل الطلب يحتاج توليد؟ ──
        path = request.path
        if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            return

        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return

        school = getattr(user, "get_school", lambda: None)()
        if school is None:
            return

        # ── فحص cache: هل تم التوليد اليوم لهذه المدرسة؟ ──
        today = timezone.localdate()
        cache_key = f"session_gen:{school.id}:{today.isoformat()}"

        try:
            if cache.get(cache_key):
                return  # تم التوليد — لا شيء للفعل
        except Exception:
            # إذا Redis غير متاح — نستخدم request attribute
            if getattr(request, "_sessions_ensured", False):
                return

        # ── التوليد الفعلي ──
        try:
            from operations.services import ScheduleService

            count = ScheduleService.ensure_sessions_for_date(school, today)

            # حفظ في cache لمدة 4 ساعات
            try:
                cache.set(cache_key, True, timeout=14400)
            except Exception:
                pass

            request._sessions_ensured = True

            if count > 0:
                logger.info(
                    "SessionMiddleware: generated %d sessions for %s",
                    count,
                    school.name,
                )

        except Exception:
            # فشل التوليد لا يكسر الطلب — يُسجَّل ويمرّ
            logger.exception("SessionAutoGenerateMiddleware failed")
