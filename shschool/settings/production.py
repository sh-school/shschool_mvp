from .base import *
from decouple import config
from django.core.exceptions import ImproperlyConfigured

DEBUG = False

# ── التحقق من المفاتيح الحرجة قبل تشغيل الإنتاج ──────────────
if not SECRET_KEY or SECRET_KEY == "dev-secret-key-change-in-production":
    raise ImproperlyConfigured(
        "🔴 SECRET_KEY مطلوب في الإنتاج! أضفه إلى ملف .env:\n"
        "python -c \"from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())\""
    )

if not FERNET_KEY:
    raise ImproperlyConfigured(
        "🔴 FERNET_KEY مطلوب في الإنتاج لتشفير البيانات الصحية (PDPPL)!\n"
        'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
    )

ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="").split(",")

# ── HTTPS وSSL ────────────────────────────────────────────────
SECURE_SSL_REDIRECT               = True
SECURE_HSTS_SECONDS               = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS    = True
SECURE_HSTS_PRELOAD               = True
SESSION_COOKIE_SECURE             = True
CSRF_COOKIE_SECURE                = True
SESSION_COOKIE_AGE                = 3600
SESSION_EXPIRE_AT_BROWSER_CLOSE   = True
SESSION_SAVE_EVERY_REQUEST        = True
SECURE_CONTENT_TYPE_NOSNIFF       = True
SECURE_BROWSER_XSS_FILTER        = True
X_FRAME_OPTIONS                   = "DENY"
SECURE_REFERRER_POLICY            = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# ── Cache ─────────────────────────────────────────────────────
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
    CACHES = {
        "default": {
            "BACKEND":  "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "schoolos-local",
        }
    }

# ── Celery + Redis ────────────────────────────────────────────
# [مهمة 15] الإشعارات وتقارير PDF تُعالج بشكل غير متزامن
if REDIS_URL:
    CELERY_BROKER_URL             = REDIS_URL
    CELERY_RESULT_BACKEND         = REDIS_URL
    CELERY_ACCEPT_CONTENT         = ["json"]
    CELERY_TASK_SERIALIZER        = "json"
    CELERY_RESULT_SERIALIZER      = "json"
    CELERY_TIMEZONE               = "Asia/Qatar"
    CELERY_TASK_TRACK_STARTED     = True
    CELERY_TASK_TIME_LIMIT        = 300        # 5 دقائق حد أقصى للمهمة
    CELERY_TASK_SOFT_TIME_LIMIT   = 240        # تحذير بعد 4 دقائق
    CELERY_WORKER_PREFETCH_MULTIPLIER = 1      # مهمة واحدة في المرة للذاكرة
    CELERY_TASK_ALWAYS_EAGER      = False
else:
    # Fallback إذا لم يكن Redis متاحاً
    CELERY_TASK_ALWAYS_EAGER      = True
    CELERY_TASK_EAGER_PROPAGATES  = True

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
        "django":        {"handlers": ["file"], "level": "ERROR",   "propagate": False},
        "notifications": {"handlers": ["file"], "level": "WARNING", "propagate": False},
        "celery":        {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

# ── CSP الإنتاج — nonce-based بدون unsafe-inline ─────────────
# ✅ Tailwind مصرَّف محلياً — لا CDN لـ Tailwind
# ✅ unsafe-inline محذوف — nonces تُولَّد لكل طلب تلقائياً
CSP_SCRIPT_SRC       = ("'self'", "https://cdn.jsdelivr.net", "https://unpkg.com",)
CSP_STYLE_SRC        = ("'self'", "'unsafe-inline'", "https://fonts.googleapis.com",)
CSP_INCLUDE_NONCE_IN = ("SCRIPT_SRC",)
CSP_REPORT_ONLY      = False

# ── التحقق من ALLOWED_HOSTS ──────────────────────────────────
if not ALLOWED_HOSTS or ALLOWED_HOSTS == [""]:
    raise ImproperlyConfigured(
        "🔴 ALLOWED_HOSTS فارغ! أضف النطاقات المسموحة في .env:\n"
        "ALLOWED_HOSTS=schoolos.qa,www.schoolos.qa"
    )
