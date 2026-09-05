"""
operations/middleware.py — توليد الحصص التلقائي وحارسُ العام الدراسيّ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Middleware يضمن وجود حصص الأسبوع الحالي لكل مدرسة.
يعمل بشكل شفاف مع كل طلب — بدون أي تدخل يدوي.

الآلية:
  1. فحص cache سريع (≈0.2ms) — إذا تم التوليد اليوم → skip
  2. إذا أول طلب في اليوم → يولّد حصص الأسبوع كامل (أحد-خميس)
  3. يحفظ في cache لمدة 4 ساعات
  4. idempotent: bulk_create(ignore_conflicts=True)

ومعه — في المِفصل اليوميّ نفسِه — حارسُ العام: يُطفئ حصصَ الجدول الباقيةَ
نشطةً من عامٍ مضى. والعامُ يتبدّل بتاريخٍ من تقويم الوزارة لا بزرّ يضغطه
أحد، فلو انتظرنا إنساناً يتذكّر لبقي جدولان نشطين في مدرسةٍ واحدة. وهذا
المِفصل يعمل بلا Celery Beat — والبيتُ مطفأٌ في الإنتاج.

الأداء:
  - Cache hit: ~0.2ms (لا overhead)
  - أول طلب في اليوم: ~10-15ms مرة واحدة فقط
  - بدون cache backend: يستخدم request attribute كـ fallback
"""

import logging
from datetime import date

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

#: آخرُ يومٍ أُنجز فيه مِفصلُ اليوم لكلّ مدرسة — في ذاكرة العمليّة نفسِها.
#:
#: طبقةٌ تحت الـcache لا بديلاً عنه: إن سقط Redis كان المِفصل يعود إلى سمةٍ
#: على الطلب فيعمل مع **كلّ** طلب — حارسُ العام وتوليدُ الحصص كلاهما — إلى
#: أن يعود Redis. وذاكرةُ العمليّة تُبقيه مرّةً في اليوم لكلّ عاملٍ مهما كان
#: حالُ الـcache، وتُوفّر رحلةَ Redis في الطلبات التالية أصلاً.
_DONE_TODAY: dict[object, date] = {}

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

        # ── هل أُنجز اليومُ لهذه المدرسة؟ ذاكرةُ العمليّة أوّلاً ثمّ الـcache ──
        today = timezone.localdate()
        if _DONE_TODAY.get(school.id) == today:
            return

        cache_key = f"session_gen:{school.id}:{today.isoformat()}"
        try:
            if cache.get(cache_key):
                _DONE_TODAY[school.id] = today
                return  # أنجزه عاملٌ آخر — لا شيء للفعل
        except (OSError, ConnectionError):
            pass  # Redis غائب — ذاكرةُ العمليّة أعلاه تكفي لمنع التكرار

        # ── التوليد الفعلي ──
        try:
            from operations.services import ScheduleService

            # حارسُ العام أوّلاً: حصصُ اليوم تُشتقّ من الجدول النشط، فلو بقي
            # جدولُ عامٍ مضى نشطاً وُلِّدت منه حصصٌ لشُعبٍ لم تعد قائمة. ومعه
            # الإسنادُ — فهو أصلُ الجدول، وبقاؤه نشطاً يُعيد إنتاج العطب.
            ScheduleService.retire_past_year_records(school)

            count = ScheduleService.ensure_sessions_for_date(school, today)

            _DONE_TODAY[school.id] = today
            # ويُخبَر العمّالُ الآخرون عبر الـcache لأربع ساعات
            try:
                cache.set(cache_key, True, timeout=14400)
            except (OSError, ConnectionError):
                pass

            if count > 0:
                logger.info(
                    "SessionMiddleware: generated %d sessions for %s",
                    count,
                    school.name,
                )

        except Exception:
            # فشل التوليد لا يكسر الطلب — يُسجَّل ويمرّ
            logger.exception("SessionAutoGenerateMiddleware failed")
