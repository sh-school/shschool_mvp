from .base import *

DEBUG = True

# ── مفتاح آمن للتطوير فقط — لا يُستخدم في الإنتاج أبداً ──────
if not SECRET_KEY:
    SECRET_KEY = "django-insecure-dev-only-do-not-use-in-production-12345"

SESSION_COOKIE_SECURE = False

# ✅ v5.1.1: Django Debug Toolbar للتطوير — يكشف N+1 queries
try:
    import debug_toolbar  # noqa: F401

    INSTALLED_APPS += ["debug_toolbar"]
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")
    INTERNAL_IPS = ["127.0.0.1"]
    DEBUG_TOOLBAR_CONFIG = {
        "SHOW_TOOLBAR_CALLBACK": lambda request: DEBUG,
        "SQL_WARNING_THRESHOLD": 100,  # ms
    }
except ImportError:
    INSTALLED_APPS += []

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ── تطوير: استخدام StaticFilesStorage العادي بدل Manifest ─────
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

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

# ── Django Channels — وضع التطوير ────────────────────────────
# إذا لم يكن Redis مشغّلاً، استخدم InMemoryChannelLayer بدلاً من Redis
# WebSocket يعمل بشكل كامل داخل نفس العملية (كافٍ للتطوير)
def _redis_running() -> bool:
    import socket
    try:
        with socket.create_connection(("127.0.0.1", 6379), timeout=0.5):
            return True
    except OSError:
        return False

if not REDIS_URL and not _redis_running():
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }
