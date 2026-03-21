import os
from pathlib import Path
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

INSTALLED_APPS = [
    "django.contrib.admin",
    "storages",
    "drf_spectacular",
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
    # ✅ v5: وحدة كنترول الاختبارات
    "exam_control.apps.ExamControlConfig",
    # ✅ v5: خرق البيانات PDPPL
    "breach.apps.BreachConfig",
    # ✅ فلترة احترافية
    "django_filters",
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
        "core.middleware.ParentConsentMiddleware",
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

DEBUG         = config("DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1,0.0.0.0").split(",")

_secret_key = config("SECRET_KEY", default="")
if not _secret_key:
    if not DEBUG:
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured(
            "SECRET_KEY مطلوب في الإنتاج — أضفه إلى ملف .env"
        )
    # في التطوير فقط: مفتاح افتراضي آمن — لا يُستخدم في الإنتاج أبداً
    import secrets
    _secret_key = "dev-only-" + secrets.token_hex(32)
SECRET_KEY = _secret_key

# ── تشفير البيانات الحساسة (PDPPL) ──────────────────────────
# أنشئ مفتاحاً جديداً: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FERNET_KEY    = config("FERNET_KEY", default="")

# ── CORS (للـ API — React Native / Mobile App) ────────────────
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:3000,http://localhost:8000"
).split(",")
CORS_ALLOW_CREDENTIALS = True

LANGUAGE_CODE = "ar"
TIME_ZONE     = "Asia/Qatar"
USE_I18N      = True
USE_TZ        = True

STATIC_URL       = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT      = BASE_DIR / "staticfiles"
MEDIA_URL        = "/media/"
MEDIA_ROOT       = config("MEDIA_ROOT", default=str(BASE_DIR / "media"))

# ── S3 / Object Storage (اختياري — يُفعَّل في الإنتاج) ──────────────
# pip install django-storages[boto3]
# اضبط USE_S3=true في .env مع متغيرات AWS_* أو نقطة نهاية S3 متوافقة (MinIO, Wasabi, Cloudflare R2)
USE_S3                  = config("USE_S3", default=False, cast=bool)
AWS_ACCESS_KEY_ID       = config("AWS_ACCESS_KEY_ID",       default="")
AWS_SECRET_ACCESS_KEY   = config("AWS_SECRET_ACCESS_KEY",   default="")
AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME", default="")
AWS_S3_REGION_NAME      = config("AWS_S3_REGION_NAME",      default="me-south-1")
AWS_S3_ENDPOINT_URL     = config("AWS_S3_ENDPOINT_URL",     default="")   # لـ MinIO / غير AWS
AWS_S3_FILE_OVERWRITE   = False
AWS_S3_SIGNATURE_VERSION = "s3v4"
AWS_DEFAULT_ACL         = "private"   # ملفات خاصة (PDPPL)
AWS_QUERYSTRING_AUTH    = True        # روابط موقعة مؤقتة
AWS_QUERYSTRING_EXPIRE  = 3600        # صالح ساعة

LOGIN_URL          = "/auth/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL= "/auth/login/"

# ── أمان الجلسات والكوكيز ─────────────────────────────────
SESSION_COOKIE_HTTPONLY     = True
SESSION_COOKIE_SAMESITE    = "Lax"
CSRF_COOKIE_HTTPONLY        = True
CSRF_COOKIE_SAMESITE        = "Lax"
CSRF_FAILURE_VIEW           = "django.views.csrf.csrf_failure"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

_AUTH_CLASSES = ["rest_framework.authentication.SessionAuthentication"]
try:
    __import__("rest_framework_simplejwt")
    _AUTH_CLASSES.append("rest_framework_simplejwt.authentication.JWTAuthentication")
except ImportError:
    pass

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": _AUTH_CLASSES,
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS":       "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS":   "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE":                   50,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": "120/minute",
    },
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
}

# ── OpenAPI (drf-spectacular) ─────────────────────────────────────────
SPECTACULAR_SETTINGS = {
    "TITLE":              "SchoolOS API",
    "DESCRIPTION":        (
        "واجهة برمجية لمنصة إدارة مدرسة الشحانية الإعدادية الثانوية للبنين\n\n"
        "**المصادقة:** Session (المتصفح) أو JWT Bearer Token (التطبيق المحمول)\n\n"
        "**الإصدار:** v1 | **الترخيص:** خاص بوزارة التربية والتعليم — دولة قطر"
    ),
    "VERSION":            "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v1/",
    "TAGS": [
        {"name": "auth",          "description": "المصادقة وبيانات المستخدم"},
        {"name": "students",      "description": "الطلاب — درجات وغياب"},
        {"name": "classes",       "description": "الفصول الدراسية ونتائجها"},
        {"name": "sessions",      "description": "الحصص الدراسية"},
        {"name": "attendance",    "description": "سجل الحضور والغياب"},
        {"name": "behavior",      "description": "المخالفات السلوكية"},
        {"name": "notifications", "description": "الإشعارات الداخلية"},
        {"name": "analytics",     "description": "مؤشرات الأداء والتحليلات"},
        {"name": "parent",        "description": "بوابة ولي الأمر"},
        {"name": "library",       "description": "المكتبة المدرسية"},
        {"name": "clinic",        "description": "العيادة المدرسية"},
    ],
}

# ── JWT (Simple JWT) ──────────────────────────────────────────────────
from datetime import timedelta
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME":  timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS":  True,
    "AUTH_HEADER_TYPES":      ("Bearer",),
    "USER_ID_FIELD":          "id",
    "USER_ID_CLAIM":          "user_id",
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
# ⚠️ unsafe-inline مطلوب مؤقتاً لـ HTMX inline handlers
# TODO: الانتقال لـ nonce-based CSP بعد تنظيف Templates
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC  = ("'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net", "https://cdnjs.cloudflare.com", "https://unpkg.com",)
CSP_STYLE_SRC   = ("'self'", "'unsafe-inline'", "https://fonts.googleapis.com", "https://cdn.jsdelivr.net",)
CSP_FONT_SRC    = ("'self'", "https://fonts.gstatic.com",)
CSP_IMG_SRC     = ("'self'", "data:", "blob:",)
CSP_CONNECT_SRC = ("'self'",)
CSP_FRAME_SRC   = ("'none'",)
CSP_OBJECT_SRC  = ("'none'",)


# ✅ v5: VAPID Push Notifications
# غيّر هذه القيم بالمفاتيح المولَّدة في .env
VAPID_PRIVATE_KEY    = os.environ.get('VAPID_PRIVATE_KEY', '').replace('\\n', '\n')
VAPID_PUBLIC_KEY     = os.environ.get('VAPID_PUBLIC_KEY', '').replace('\\n', '\n')
VAPID_PUBLIC_KEY_B64 = os.environ.get('VAPID_PUBLIC_KEY_B64', '')
VAPID_CLAIMS_EMAIL   = os.environ.get('VAPID_CLAIMS_EMAIL', 'admin@shahaniya.edu.qa')

# ✅ DPO — مسؤول حماية البيانات (PDPPL م.17)
DPO_NAME  = os.environ.get('DPO_NAME',  'سفيان احمد محمد مسيف')
DPO_EMAIL = os.environ.get('DPO_EMAIL', 's.mesyef0904@education.qa')
DPO_PHONE = os.environ.get('DPO_PHONE', '55296286')
