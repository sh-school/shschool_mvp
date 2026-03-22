from .base import *

DEBUG = True

# ── مفتاح آمن للتطوير فقط — لا يُستخدم في الإنتاج أبداً ──────
if not SECRET_KEY:
    SECRET_KEY = "django-insecure-dev-only-do-not-use-in-production-12345"

SESSION_COOKIE_SECURE = False

INSTALLED_APPS += []

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ── تطوير: تعطيل CSP لتجنب تعارضه مع Tailwind CDN ──────────
MIDDLEWARE = [m for m in MIDDLEWARE if m != "csp.middleware.CSPMiddleware"]

CSP_SCRIPT_SRC = (
    "'self'",
    "'unsafe-inline'",
    "'unsafe-eval'",
    "https://cdn.jsdelivr.net",
    "https://cdnjs.cloudflare.com",
    "https://cdn.tailwindcss.com",
    "https://unpkg.com",
)

# ── Celery — وضع التطوير ─────────────────────────────────────
# CELERY_TASK_ALWAYS_EAGER = True يُشغّل المهام مباشرة بدون broker
# مناسب للتطوير المحلي — لا يحتاج Redis مثبتاً
REDIS_URL = config("REDIS_URL", default="")

if REDIS_URL:
    # Redis متوفر — استخدمه
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL
    CELERY_TASK_ALWAYS_EAGER = False
else:
    # لا Redis — شغّل المهام synchronously (مناسب للتطوير فقط)
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True
    CELERY_BROKER_URL = "memory://"
    CELERY_RESULT_BACKEND = "cache+memory://"
