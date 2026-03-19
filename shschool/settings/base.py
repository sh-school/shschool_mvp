import os
from pathlib import Path
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_htmx",
    "core.apps.CoreConfig",
    "operations.apps.OperationsConfig",
    "staging.apps.StagingConfig",
    "quality.apps.QualityConfig",
    "assessments.apps.AssessmentsConfig",
    "parents.apps.ParentsConfig",
    "reports.apps.ReportsConfig",
    "analytics.apps.AnalyticsConfig",
    "notifications.apps.NotificationsConfig",
    "clinic.apps.ClinicConfig",
    "transport.apps.TransportConfig",
    "behavior.apps.BehaviorConfig",
    "library.apps.LibraryConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.SchoolPermissionMiddleware",
    "core.middleware.CurrentUserMiddleware",
    "csp.middleware.CSPMiddleware",
]

ROOT_URLCONF = "shschool.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.school_context",
            ],
        },
    },
]

WSGI_APPLICATION = "shschool.wsgi.application"

AUTH_USER_MODEL = "core.CustomUser"

DATABASES = {
    "default": {
        "ENGINE":   "django.db.backends.postgresql",
        "NAME":     config("DB_NAME",     default="shschool_db"),
        "USER":     config("DB_USER",     default="shschool_user"),
        "PASSWORD": config("DB_PASSWORD", default="shschool_pass"),
        "HOST":     config("DB_HOST",     default="localhost"),
        "PORT":     config("DB_PORT",     default="5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

SECRET_KEY    = config("SECRET_KEY", default="dev-secret-key-change-in-production")

# ── تشفير البيانات الحساسة (PDPPL) ──────────────────────────
# أنشئ مفتاحاً جديداً: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FERNET_KEY    = config("FERNET_KEY", default="")
DEBUG         = config("DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1,0.0.0.0").split(",")

LANGUAGE_CODE = "ar"
TIME_ZONE     = "Asia/Qatar"
USE_I18N      = True
USE_TZ        = True

STATIC_URL       = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT      = BASE_DIR / "staticfiles"
MEDIA_URL        = "/media/"
MEDIA_ROOT       = config("MEDIA_ROOT", default=str(BASE_DIR / "media"))

LOGIN_URL          = "/auth/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL= "/auth/login/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

# ── البريد الإلكتروني ──────────────────────────────
EMAIL_BACKEND      = config("EMAIL_BACKEND",       default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST         = config("EMAIL_HOST",          default="smtp.gmail.com")
EMAIL_PORT         = config("EMAIL_PORT",          default=587, cast=int)
EMAIL_USE_TLS      = config("EMAIL_USE_TLS",       default=True, cast=bool)
EMAIL_HOST_USER    = config("EMAIL_HOST_USER",     default="")
EMAIL_HOST_PASSWORD= config("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL",  default="noreply@schoolos.qa")

# ── Content Security Policy ───────────────────────────────
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC  = ("'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net", "https://cdnjs.cloudflare.com",)
CSP_STYLE_SRC   = ("'self'", "'unsafe-inline'", "https://fonts.googleapis.com", "https://cdn.jsdelivr.net",)
CSP_FONT_SRC    = ("'self'", "https://fonts.gstatic.com",)
CSP_IMG_SRC     = ("'self'", "data:", "blob:",)
CSP_CONNECT_SRC = ("'self'",)
CSP_FRAME_SRC   = ("'none'",)
CSP_OBJECT_SRC  = ("'none'",)

