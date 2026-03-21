"""
shschool/settings/testing.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━
إعدادات خاصة بـ CI / pytest فقط.
يُفعَّل عبر: DJANGO_SETTINGS_MODULE=shschool.settings.testing
"""
from .base import *  # noqa

# ── أمان ──────────────────────────────────────────────────────────
DEBUG      = False
SECRET_KEY = "ci-testing-secret-key-not-for-production-do-not-use"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

# ── قاعدة البيانات — PostgreSQL من CI env vars ─────────────────
DATABASES = {
    "default": {
        "ENGINE":   "django.db.backends.postgresql",
        "NAME":     "test_db",
        "USER":     "test_user",
        "PASSWORD": "test_pass",
        "HOST":     "localhost",
        "PORT":     "5432",
        "TEST":     {"NAME": "test_db"},
    }
}

# ── Cache — LocMem بدل Redis (أسرع في الاختبارات) ─────────────
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# ── البريد الإلكتروني — dummy لا يُرسل شيئاً ──────────────────
EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"

# ── Celery — تشغيل المهام مباشرة بدون broker ──────────────────
CELERY_TASK_ALWAYS_EAGER     = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL            = "memory://"
CELERY_RESULT_BACKEND        = "cache+memory://"

# ── S3 — معطّل في الاختبارات ───────────────────────────────────
USE_S3 = False

# ── CSP — معطّل لتبسيط الاختبارات ─────────────────────────────
MIDDLEWARE = [m for m in MIDDLEWARE if m != "csp.middleware.CSPMiddleware"]

# ── كلمات المرور — تحقق مبسّط (أسرع) ─────────────────────────
AUTH_PASSWORD_VALIDATORS = []

# ── Media — مؤقت أثناء الاختبارات ─────────────────────────────
import tempfile
MEDIA_ROOT = tempfile.mkdtemp()

# ── VAPID — قيم وهمية للاختبار ────────────────────────────────
VAPID_PRIVATE_KEY    = ""
VAPID_PUBLIC_KEY     = ""
VAPID_PUBLIC_KEY_B64 = ""
VAPID_CLAIMS_EMAIL   = "test@test.com"

# ── FERNET — مفتاح وهمي للاختبار ──────────────────────────────
# يجب أن يكون base64 url-safe 32 bytes
FERNET_KEY = "dGVzdC1mZXJuZXQta2V5LTMyLWJ5dGVzLWZvcmNpLS0="

# Rate Limiting disabled in tests
RATELIMIT_ENABLE = False
