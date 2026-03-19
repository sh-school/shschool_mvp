from .base import *

DEBUG = True
SESSION_COOKIE_SECURE = False

INSTALLED_APPS += []

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

