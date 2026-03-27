from decouple import config
from django.core.exceptions import ImproperlyConfigured

from .base import *

DEBUG = False

# ✅ v5.1.1: IPs المسموحة للوصول إلى /metrics (Prometheus)
METRICS_ALLOWED_IPS = config("METRICS_ALLOWED_IPS", default="127.0.0.1,::1,10.0.0.1").split(",")

# ══════════════════════════════════════════════════════════════
# ✅ v5.1: Sentry — مراقبة الأخطاء (PDPPL: send_default_pii=False)
# ══════════════════════════════════════════════════════════════
SENTRY_DSN = config("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            RedisIntegration(),
        ],
        traces_sample_rate=0.1,  # 10% من الطلبات للـ performance tracing
        send_default_pii=False,  # ← PDPPL: لا بيانات شخصية للطلاب
        environment="production",
        release=config("APP_VERSION", default="v5.1"),
    )

# ── التحقق من المفاتيح الحرجة قبل تشغيل الإنتاج ──────────────
if not SECRET_KEY or SECRET_KEY == "dev-secret-key-change-in-production":
    raise ImproperlyConfigured(
        "🔴 SECRET_KEY مطلوب في الإنتاج! أضفه إلى ملف .env:\n"
        'python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"'
    )

if not FERNET_KEY:
    raise ImproperlyConfigured(
        "🔴 FERNET_KEY مطلوب في الإنتاج لتشفير البيانات الصحية (PDPPL)!\n"
        'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
    )

ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="").split(",")

# ── HTTPS وSSL ────────────────────────────────────────────────
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_AGE = 3600
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# ── Cache ─────────────────────────────────────────────────────
REDIS_URL = config("REDIS_URL", default="")

if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {"socket_timeout": 5},
        }
    }
    SESSION_ENGINE = "django.contrib.sessions.backends.cache"
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "schoolos-local",
        }
    }

# ── Celery + Redis ────────────────────────────────────────────
# [مهمة 15] الإشعارات وتقارير PDF تُعالج بشكل غير متزامن
if REDIS_URL:
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL
    CELERY_ACCEPT_CONTENT = ["json"]
    CELERY_TASK_SERIALIZER = "json"
    CELERY_RESULT_SERIALIZER = "json"
    CELERY_TIMEZONE = "Asia/Qatar"
    CELERY_TASK_TRACK_STARTED = True
    CELERY_TASK_TIME_LIMIT = 300  # 5 دقائق حد أقصى للمهمة
    CELERY_TASK_SOFT_TIME_LIMIT = 240  # تحذير بعد 4 دقائق
    CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # مهمة واحدة في المرة للذاكرة
    CELERY_TASK_ALWAYS_EAGER = False
else:
    # Fallback إذا لم يكن Redis متاحاً
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True

# ── Logging ───────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "security": {
            "format": "SECURITY {levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    # ✅ v5.3: فلتر إخفاء البيانات الشخصية — PDPPL م.13
    "filters": {
        "pii_masking": {
            "()": "core.logging_filters.PIIMaskingFilter",
        },
    },
    "handlers": {
        "file": {
            "level": "WARNING",
            # ✅ v5.1: RotatingFileHandler بدلاً من FileHandler
            # يدير حجم الملف تلقائياً: 10MB × 5 نسخ = 50MB حد أقصى
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs/django.log",
            "maxBytes": 10 * 1024 * 1024,  # 10 MB
            "backupCount": 5,
            "encoding": "utf-8",
            "formatter": "verbose",
            "filters": ["pii_masking"],  # ✅ v5.3: إخفاء PII
        },
        "security_file": {
            "level": "WARNING",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs/security.log",
            "maxBytes": 5 * 1024 * 1024,  # 5 MB
            "backupCount": 10,  # نحتفظ بـ 10 نسخ للأمان
            "encoding": "utf-8",
            "formatter": "security",
            "filters": ["pii_masking"],  # ✅ v5.3: إخفاء PII
        },
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["pii_masking"],  # ✅ v5.3: إخفاء PII
        },
    },
    "root": {"handlers": ["file", "console"], "level": "WARNING"},
    "loggers": {
        "django": {"handlers": ["file"], "level": "WARNING", "propagate": False},
        "django.security": {"handlers": ["security_file"], "level": "WARNING", "propagate": False},
        "django.request": {"handlers": ["file"], "level": "WARNING", "propagate": False},
        "notifications": {"handlers": ["file"], "level": "INFO", "propagate": False},
        "notifications.hub": {"handlers": ["file"], "level": "INFO", "propagate": False},
        "celery": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "core": {"handlers": ["security_file"], "level": "WARNING", "propagate": False},
        # ✅ v5.1: Channels & WebSocket logging
        "channels": {"handlers": ["file"], "level": "WARNING", "propagate": False},
        "daphne": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}

# ── CSP في الإنتاج — Enforce (لا Report-Only) ─────────────────
# Tailwind مصرَّف محلياً — لا حاجة لـ CDN للـ CSS
CSP_SCRIPT_SRC = (
    "'self'",
    "https://cdn.jsdelivr.net",
    "https://unpkg.com",
)
# ✅ v5.2: nonce-based style-src — إزالة unsafe-inline
# style attributes في القوالب يجب أن تُنقل إلى CSS classes
# أو تُضاف عبر <style nonce="{{ request.csp_nonce }}">
CSP_STYLE_SRC = (
    "'self'",
    "https://fonts.googleapis.com",
)
CSP_INCLUDE_NONCE_IN = ["script-src", "style-src"]  # ✅ nonce لكليهما
CSP_REPORT_ONLY = False  # ← Enforce: أي script/style بلا nonce سيُحجب
# ✅ v5.2: CSP Reporting — تسجيل الانتهاكات
CSP_REPORT_URI = config("CSP_REPORT_URI", default="")

# ── S3 Object Storage للملفات (media) ────────────────────────
# فعّله بـ USE_S3=true في .env ومتغيرات AWS_* / نقطة نهاية S3 متوافقة
if USE_S3:
    if not all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_STORAGE_BUCKET_NAME]):
        import logging

        logging.getLogger(__name__).warning(
            "⚠️ USE_S3=true لكن AWS_* credentials ناقصة — سيُستخدم التخزين المحلي"
        )
    else:
        INSTALLED_APPS = [a for a in INSTALLED_APPS if a != "storages"] + ["storages"]
        STORAGES = {
            # ملفات المستخدمين (library PDFs، صور) → S3 خاص
            "default": {
                "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
                "OPTIONS": {
                    "bucket_name": AWS_STORAGE_BUCKET_NAME,
                    "region_name": AWS_S3_REGION_NAME,
                    "endpoint_url": AWS_S3_ENDPOINT_URL or None,
                    "location": "media",
                    "file_overwrite": False,
                    "default_acl": "private",
                    "querystring_auth": True,
                    "querystring_expire": AWS_QUERYSTRING_EXPIRE,
                    "object_parameters": {
                        "ContentDisposition": "inline",
                    },
                },
            },
            # الملفات الثابتة → WhiteNoise (Brotli + GZip + hash → cache ∞)
            "staticfiles": {
                "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
            },
        }
        # MEDIA_URL → روابط S3 (أو CDN)
        _cdn = config("AWS_S3_CUSTOM_DOMAIN", default="")
        if _cdn:
            MEDIA_URL = f"https://{_cdn}/media/"
        elif AWS_S3_ENDPOINT_URL:
            MEDIA_URL = f"{AWS_S3_ENDPOINT_URL}/{AWS_STORAGE_BUCKET_NAME}/media/"
        else:
            MEDIA_URL = (
                f"https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/media/"
            )

# ── CDN Configuration (Cloudflare / CloudFront) ─────────────────
CDN_DOMAIN = config("CDN_DOMAIN", default="")
if CDN_DOMAIN:
    STATIC_URL = f"https://{CDN_DOMAIN}/static/"
    # Media continues to use signed S3 URLs if USE_S3 is enabled

# ── التحقق من ALLOWED_HOSTS ──────────────────────────────────
if not ALLOWED_HOSTS or ALLOWED_HOSTS == [""]:
    raise ImproperlyConfigured(
        "🔴 ALLOWED_HOSTS فارغ! أضف النطاقات المسموحة في .env:\n"
        "ALLOWED_HOSTS=schoolos.qa,www.schoolos.qa"
    )

# ── التحقق من CORS في الإنتاج ────────────────────────────────
# يمنع CORS_ALLOWED_ORIGINS الافتراضي (localhost) في الإنتاج
_unsafe_cors = [o for o in CORS_ALLOWED_ORIGINS if "localhost" in o or "127.0.0.1" in o]
if _unsafe_cors:
    import logging

    logging.getLogger(__name__).warning(
        "⚠️ CORS_ALLOWED_ORIGINS يحتوي على origins محلية في الإنتاج: %s — "
        "عيّن CORS_ALLOWED_ORIGINS في .env بالنطاقات الصحيحة (https://...)",
        _unsafe_cors,
    )
