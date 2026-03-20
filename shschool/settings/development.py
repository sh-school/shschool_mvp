from .base import *

DEBUG = True
SESSION_COOKIE_SECURE =False

INSTALLED_APPS += []

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


# ── تطوير: تعطيل CSP لتجنب تعارضه مع Tailwind CDN ──────────
# في الإنتاج يبقى CSP مفعلاً في base.py
MIDDLEWARE = [m for m in MIDDLEWARE if m != "csp.middleware.CSPMiddleware"]

# Tailwind JIT يحتاج unsafe-eval (للـ arbitrary values مثل bg-[#8A1538])
CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'", "'unsafe-eval'",
                  "https://cdn.jsdelivr.net", "https://cdnjs.cloudflare.com",
                  "https://cdn.tailwindcss.com", "https://unpkg.com",)
