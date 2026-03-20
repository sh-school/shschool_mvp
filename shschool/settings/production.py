from .base import *
from decouple import config

# ══════════════════════════════════════════════════════════════
#  إعدادات الإنتاج — SchoolOS
#  تأكد من ضبط متغيرات البيئة في .env قبل النشر
# ══════════════════════════════════════════════════════════════

DEBUG = False

# ── المضيفون المسموح بهم ──────────────────────────────────────
# أضف الدومين الحقيقي في .env:  ALLOWED_HOSTS=schoolos.shahaniya.edu.qa
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="").split(",")

# ── HTTPS وSSL ────────────────────────────────────────────────
# [مهمة 2] إعادة توجيه HTTP → HTTPS تلقائياً
SECURE_SSL_REDIRECT               = True

# HSTS — يخبر المتصفح بعدم الاتصال بـ HTTP أبداً لمدة سنة
SECURE_HSTS_SECONDS               = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS    = True
SECURE_HSTS_PRELOAD               = True   # أُضيف: يسمح بالتسجيل في قائمة preload

# ── Cookies الآمنة ────────────────────────────────────────────
SESSION_COOKIE_SECURE             = True
CSRF_COOKIE_SECURE                = True

# ── الجلسات ──────────────────────────────────────────────────
# [مهمة 3] انتهاء الجلسة بعد ساعة من الخمول
SESSION_COOKIE_AGE                = 3600          # ثانية = 1 ساعة
SESSION_EXPIRE_AT_BROWSER_CLOSE   = True          # انتهاء عند إغلاق المتصفح
SESSION_SAVE_EVERY_REQUEST        = True          # تجديد العداد عند كل طلب

# ── حماية إضافية ─────────────────────────────────────────────
SECURE_CONTENT_TYPE_NOSNIFF       = True
SECURE_BROWSER_XSS_FILTER        = True   # أُضيف: حماية XSS في المتصفح القديم
X_FRAME_OPTIONS                   = "DENY"

# ── Cache ─────────────────────────────────────────────────────
# Redis cache — يعمل بدون Redis في بيئة التطوير (Fallback تلقائي)
REDIS_URL = config("REDIS_URL", default="")

if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND":  "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS":  {"socket_timeout": 5},
        }
    }
    SESSION_ENGINE = "django.contrib.sessions.backends.cache"
else:
    # Fallback — مناسب للتطوير المحلي فقط
    CACHES = {
        "default": {
            "BACKEND":  "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "schoolos-local",
        }
    }

# ── Logging ───────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{levelname} {asctime} {module} {message}", "style": "{"},
    },
    "handlers": {
        "file": {
            "level": "ERROR",
            "class": "logging.FileHandler",
            "filename": BASE_DIR / "logs/django.log",
            "formatter": "verbose",
        },
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {"handlers": ["file", "console"], "level": "WARNING"},
    "loggers": {
        "django": {"handlers": ["file"], "level": "ERROR", "propagate": False},
    },
}
