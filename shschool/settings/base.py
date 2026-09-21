import os
import sys
from pathlib import Path

from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ── GTK3/Pango لـ WeasyPrint على Windows (MSYS2) ──
_gtk_bin = Path("C:/msys64/mingw64/bin")
if sys.platform == "win32" and _gtk_bin.exists():
    os.environ["PATH"] = str(_gtk_bin) + ";" + os.environ.get("PATH", "")

# ── السنة الدراسية الحالية — غيّرها هنا فقط ──────────────────
CURRENT_ACADEMIC_YEAR: str = "2025-2026"

# ── إصدار المنصة — يظهر في الفوتر ─────────────────────────────
PLATFORM_VERSION: str = "5.5"

INSTALLED_APPS = [
    # ✅ v5.1: daphne يجب أن يكون أول app لتفعيل ASGI بشكل صحيح
    "daphne",
    "channels",
    "django_prometheus",
    "django.contrib.admin",
    "storages",
    "drf_spectacular",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
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
    # ✅ v7: شؤون الطلاب
    "student_affairs.apps.StudentAffairsConfig",
    # ✅ v7: شؤون الموظفين
    "staff_affairs.apps.StaffAffairsConfig",
    # ✅ REQ-SH-002: إدارة الشؤون الأكاديمية (Client #001)
    "academic_management.apps.AcademicManagementConfig",
    # ✅ SPRINT-DF-001: أرسل إلى المطوّر (Developer Feedback) — PRD-SOS-DEV-FEEDBACK-v1.0
    "developer_feedback.apps.DeveloperFeedbackConfig",
    # ✅ مركز معلومات الطلبة — ملفّ الطالب الجامع وملاحظات الجهات الخمس
    "student_info.apps.StudentInfoConfig",
    "wings.apps.WingsConfig",
    # خارطة تجويد المنصّة — لمطوّر المنصّة وحدَه (أدوات المطوّر)
    "roadmap.apps.RoadmapConfig",
    # الحوكمة وحماية البيانات: المحو والاحتفاظ وتدوير المفاتيح ووصول الملفّات (ADR-0004)
    "governance.apps.GovernanceConfig",
    # ✅ فلترة احترافية
    "django_filters",
    # ✅ [SEC-02] قائمة حظر توكنات التحديث بعد التدوير (JWT) — تتطلب migrate
    "rest_framework_simplejwt.token_blacklist",
    # ✅ v5.4: حماية من هجمات القوة الغاشمة (Brute Force)
    "axes",
]

MIDDLEWARE = [
    # ✅ v5.1: Prometheus يجب أن يكون أول وآخر middleware
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # ✅ WhiteNoise: static files مع Brotli/GZip + cache headers مثالية
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # ✅ CORS — يجب أن يكون قبل CommonMiddleware
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # ✅ v5.4: axes يجب أن يكون بعد AuthenticationMiddleware مباشرةً
    "axes.middleware.AxesMiddleware",
    # ✅ v5.6: RLS — يجب أن يضبط السياق قبل أي middleware يستعلم جداول محميّة
    "core.middleware_rls.RLSMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.SchoolPermissionMiddleware",
    # `request.school` — مدرسةُ المستخدم تُحسب مرّةً بعد حارس المسارات (الذي حمّل العضويّة)
    "core.middleware.SchoolContextMiddleware",
    "core.middleware.CurrentUserMiddleware",
    "core.middleware.SentryScopeMiddleware",  # ✅ v5.5: Sentry context (school_id + role)
    "operations.middleware.SessionAutoGenerateMiddleware",  # ✅ توليد الحصص تلقائياً — بدون Celery
    "csp.middleware.CSPMiddleware",
    # الإلزامُ بتغيير كلمة المرور قبل موافقة وليّ الأمر: من لم يُبدّل كلمتَه لا يوافق بها.
    "core.middleware.ForcePasswordChangeMiddleware",
    "core.middleware.TwoFactorEnforcementMiddleware",
    # المفعِّلُ لا تُقبل جلستُه بلا رمزٍ أُدخل فيها — يسدّ ما يفتح جلسةً بكلمة المرور وحدَها
    "core.mfa_session.MfaSessionMiddleware",
    "core.middleware.ParentConsentMiddleware",
    # صفحةُ المسجَّل لا تُخزَّن: طزاجةٌ بعد النشر، وخصوصيّةٌ على جهازٍ مشترك
    "core.middleware.PrivateHtmlNoStoreMiddleware",
    # ✅ v5.1: Prometheus آخر middleware لقياس وقت الاستجابة كاملاً
    "django_prometheus.middleware.PrometheusAfterMiddleware",
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
                "core.context_processors.permissions_context",
                "core.context_processors.quality_nav_context",
            ],
        },
    },
]

WSGI_APPLICATION = "shschool.wsgi.application"
ASGI_APPLICATION = "shschool.asgi.application"

# ── Django Channels — Channel Layer (Redis) ────────────────────────────
CHANNEL_LAYER_SOCKET_TIMEOUT = 15  # ثانية؛ يجب أن تفوق RedisChannelLayer.brpop_timeout (5)
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            # مهلةُ القراءة صريحةٌ: redis-py ≥ 8 صار افتراضُها 5s (كان بلا مهلة)،
            # وchannels_redis يقرأ بـBZPOPMIN بمهلة `brpop_timeout` = 5s على الاتصال
            # نفسه — فتتساوى المهلتان ويسقط كلُّ مستهلكٍ خامل بـ«Timeout reading from
            # redis» بعد ~5s. تبقى أكبر من 5s بهامشٍ يكشف الاتصالَ الميّت.
            "hosts": [
                {
                    "address": config("REDIS_URL", default="redis://localhost:6379/0"),
                    "socket_timeout": CHANNEL_LAYER_SOCKET_TIMEOUT,
                    "socket_connect_timeout": 5,
                }
            ],
            "capacity": 1500,  # حد الرسائل لكل channel
            "expiry": 30,  # TTL الرسالة بالثواني
        },
    }
}

AUTH_USER_MODEL = "core.CustomUser"

# ✅ v5.1.1: HMAC Authentication Backend — يبحث عبر HMAC(national_id) مع fallback
# ✅ v5.4: axes.backends.AxesStandaloneBackend يجب أن يكون أول backend (يمنع المقفولين)
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "core.backends.HMACAuthBackend",
]

# ── قاعدة البيانات ─────────────────────────────────────────
# v5.4.1: دعم DATABASE_URL (Railway/Heroku/Render) مع fallback للمتغيرات المنفصلة
_database_url = config("DATABASE_URL", default="")
if _database_url:
    import dj_database_url

    DATABASES = {
        "default": dj_database_url.parse(
            _database_url,
            conn_max_age=config("DB_CONN_MAX_AGE", default=600, cast=int),
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": config("DB_NAME", default="shschool_db"),
            "USER": config("DB_USER", default="shschool_user"),
            "PASSWORD": config("DB_PASSWORD", default=""),
            "HOST": config("DB_HOST", default="localhost"),
            "PORT": config("DB_PORT", default="5432"),
            "CONN_MAX_AGE": config("DB_CONN_MAX_AGE", default=600, cast=int),
            "CONN_HEALTH_CHECKS": True,
        }
    }

#: تدويرُ كلمة مرور المنتسبين — كلُّ كم يوماً يُجبَر على تغييرها عند الدخول (قرار 2026-09-08: 90).
#: يسري على أصحاب عضويّةٍ نشطةٍ من الكادر وحدَهم، لا على الطلبة وأولياء الأمور. والصفرُ يعطّله.
PASSWORD_ROTATION_DAYS = config("PASSWORD_ROTATION_DAYS", default=90, cast=int)
# قرار 2026-09-14: المصادقةُ الثنائيّة إلزاميّةٌ لكلّ منتسبٍ من الكادر (لا الطلبةَ وأولياءَ
# الأمور). من لم يفعّلها لا يبلغ صفحةً غيرَ صفحة الإعداد. وإطفاءُ الرايةِ **تجميدٌ كامل**:
# لا إلزامَ ولا سؤالَ عن رمزٍ حتى للمفعِّل (سرُّه يبقى)، فالدخولُ بكلمة المرور وحدَها.
TWO_FACTOR_REQUIRED_FOR_STAFF = config("TWO_FACTOR_REQUIRED_FOR_STAFF", default=True, cast=bool)

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {"NAME": "core.validators.StrongPasswordValidator"},
]

DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1").split(",")

_secret_key = config("SECRET_KEY", default="")
if not _secret_key:
    if not DEBUG:
        from django.core.exceptions import ImproperlyConfigured

        raise ImproperlyConfigured("SECRET_KEY مطلوب في الإنتاج — أضفه إلى ملف .env")
    # في التطوير فقط: مفتاح افتراضي آمن — لا يُستخدم في الإنتاج أبداً
    import secrets

    _secret_key = "dev-only-" + secrets.token_hex(32)
SECRET_KEY = _secret_key

# ── تشفير البيانات الحساسة (PDPPL) ──────────────────────────
# أنشئ مفتاحاً جديداً: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FERNET_KEY = config("FERNET_KEY", default="")
# ✅ v5.2: مفاتيح قديمة لدعم key rotation (مفصولة بفاصلة)
FERNET_OLD_KEYS = config("FERNET_OLD_KEYS", default="")
if not FERNET_KEY and not DEBUG:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(
        'FERNET_KEY مطلوب في الإنتاج — أنشئ مفتاحاً: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
    )

# ── كلمة سر حماية ملفات Excel (لا تُكتب في الكود) ────────────
EXCEL_PROTECTION_PASSWORD = config("EXCEL_PROTECTION_PASSWORD", default="")
if not EXCEL_PROTECTION_PASSWORD and not DEBUG:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured("EXCEL_PROTECTION_PASSWORD مطلوب في الإنتاج — أضفه إلى ملف .env")

# ── CORS (للـ API — React Native / Mobile App) ────────────────
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in config(
        "CORS_ALLOWED_ORIGINS", default="http://localhost:3000,http://localhost:8000"
    ).split(",")
    if origin.strip()
]
CORS_ALLOW_CREDENTIALS = True
# ✅ v5.2: منع credentials مع wildcard وتقييد الـ headers و methods
CORS_ALLOW_METHODS = [
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "OPTIONS",
]
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "x-csrftoken",
    "x-requested-with",
]

LANGUAGE_CODE = "ar"
TIME_ZONE = "Asia/Qatar"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = config("MEDIA_ROOT", default=str(BASE_DIR / "media"))

# ── التخزين الافتراضي: قاعدة البيانات (يدوم على Railway المؤقّت + يُنسَخ مع القاعدة) ──
# تتجاوزه dev/prod بنفس الـ default؛ يُستثنى عند USE_S3 في الإنتاج.
STORAGES = {
    "default": {"BACKEND": "core.db_storage.DatabaseStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# ── S3 / Object Storage (اختياري — يُفعَّل في الإنتاج) ──────────────
# pip install django-storages[boto3]
# اضبط USE_S3=true في .env مع متغيرات AWS_* أو نقطة نهاية S3 متوافقة (MinIO, Wasabi, Cloudflare R2)
USE_S3 = config("USE_S3", default=False, cast=bool)
AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID", default="")
AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY", default="")
AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME", default="")
AWS_S3_REGION_NAME = config("AWS_S3_REGION_NAME", default="me-south-1")
AWS_S3_ENDPOINT_URL = config("AWS_S3_ENDPOINT_URL", default="")  # لـ MinIO / غير AWS
AWS_S3_FILE_OVERWRITE = False
AWS_S3_SIGNATURE_VERSION = "s3v4"
AWS_DEFAULT_ACL = "private"  # ملفات خاصة (PDPPL)
AWS_QUERYSTRING_AUTH = True  # روابط موقعة مؤقتة
AWS_QUERYSTRING_EXPIRE = 3600  # صالح ساعة

LOGIN_URL = "/auth/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/auth/login/"

# ── أمان الجلسات والكوكيز ─────────────────────────────────
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
# [P2-A] لا JavaScript يقرأ كوكي CSRF. الرمز يأتي من الحقل المخفي في DOM الذي
# يضعه base/base.html لكل مستخدم مُعتمَد، فلا حاجة لإتاحة الكوكي للسكربتات.
# عقد أمني موحَّد عبر البيئات عمداً: وضعه في production وحده يجعل التطوير
# والاختبار يمرّان بسلوك مختلف، فينكشف أي كاسر بعد النشر لا قبله.
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_FAILURE_VIEW = "django.views.csrf.csrf_failure"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# بابُ JWT مغلقٌ ما لم يُفتح صراحةً. كان مفتوحاً «للتطبيق المحمول المستقبليّ»
# ولم يُصدَر منه رمزٌ واحد (فحصُ الإنتاج 2026-09-16)، وهو يتجاوز ما يحمي
# دخولَ الجلسة: لا ثنائيّة، ولا axes، ولا حدَّ للمحاولات. فلا مساراتِ رموز
# ولا مُصادِقَ رموز حتى يُبنى التطبيقُ ويُحرَس الباب (P1-1).
API_JWT_ENABLED = config("API_JWT_ENABLED", default=False, cast=bool)

_AUTH_CLASSES = ["rest_framework.authentication.SessionAuthentication"]
if API_JWT_ENABLED:
    _AUTH_CLASSES.append("rest_framework_simplejwt.authentication.JWTAuthentication")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": _AUTH_CLASSES,
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "30/minute",
        "user": "120/minute",
        "login": "5/minute",
        "burst": "60/minute",  # حماية burst للـ endpoints الحساسة
        "sensitive": "10/minute",  # endpoints حساسة (تغيير كلمة السر، etc.)
    },
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
}

# ── OpenAPI (drf-spectacular) ─────────────────────────────────────────
SPECTACULAR_SETTINGS = {
    "TITLE": "SchoolOS API",
    "DESCRIPTION": (
        "واجهة برمجية لمنصّة SchoolOS لإدارة المدارس\n\n"
        "**المصادقة:** Session (المتصفح) أو JWT Bearer Token (التطبيق المحمول)\n\n"
        "**الإصدار:** v1 | **الترخيص:** خاص بوزارة التربية والتعليم — دولة قطر"
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v1/",
    "TAGS": [
        {"name": "auth", "description": "المصادقة وبيانات المستخدم"},
        {"name": "students", "description": "الطلاب — درجات وغياب"},
        {"name": "classes", "description": "الفصول الدراسية ونتائجها"},
        {"name": "sessions", "description": "الحصص الدراسية"},
        {"name": "attendance", "description": "سجل الحضور والغياب"},
        {"name": "behavior", "description": "المخالفات السلوكية"},
        {"name": "notifications", "description": "الإشعارات الداخلية"},
        {"name": "analytics", "description": "مؤشرات الأداء والتحليلات"},
        {"name": "parent", "description": "بوابة ولي الأمر"},
        {"name": "library", "description": "المكتبة المدرسية"},
        {"name": "clinic", "description": "العيادة المدرسية"},
    ],
}

# ── JWT (Simple JWT) ──────────────────────────────────────────────────
from datetime import timedelta

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,  # ✅ [SEC-02] إبطال توكن التحديث القديم بعد التدوير
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# ── البريد الإلكتروني ──────────────────────────────
EMAIL_BACKEND = config("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = config("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="noreply@schoolos.qa")

# ── Content Security Policy ───────────────────────────────
# `django-csp==4.0` يقرأ `CONTENT_SECURITY_POLICY` وحده. وكانت الإعدادات هنا
# بصيغة `CSP_*` القديمة التي تخلّت عنها المكتبة، فلم تُقرأ منذ الترقية: لا
# ترويسةَ CSP تُرسَل أصلاً — والإعدادات قائمةٌ تُوهم من يقرأها بأن الحماية مفعّلة.
#
# و`NONCE` في `script-src` يعني أن المتصفّح **يتجاهل `'unsafe-inline'` للسكربتات
# تماماً**، فكل `<script>` داخليّ يلزمه `nonce="{{ request.csp_nonce }}"`.
#
# و`'unsafe-inline'` باقٍ في `style-src` عن قصد لا عن تساهل: القوالب تحمل ٧٣٢
# سمة `style="…"`، والسمات لا يُغنّي عنها nonce. ونقلُها إلى أصناف CSS عملٌ
# مستقلّ يسبق إزالتها.
from csp.constants import NONCE, SELF

CSP_BASE_DIRECTIVES = {
    "default-src": [SELF],
    "script-src": [
        SELF,
        NONCE,
        "https://cdn.jsdelivr.net",
        "https://cdnjs.cloudflare.com",
        "https://unpkg.com",
    ],
    "style-src": [
        SELF,
        "'unsafe-inline'",
        "https://fonts.googleapis.com",
        "https://cdn.jsdelivr.net",
    ],
    "font-src": [SELF, "https://fonts.gstatic.com"],
    "img-src": [SELF, "data:", "blob:"],
    "connect-src": [SELF, "wss:", "ws:"],  # wss: مطلوب للـWebSocket
    # 'self' لا 'none': صفحة استمارة الزيارة تعرض ملفّ الـPDF في إطارٍ من الأصل نفسه.
    "frame-src": [SELF],
    "object-src": ["'none'"],
}

CSP_REPORT_ONLY = config("CSP_REPORT_ONLY", default=True, cast=bool)

if CSP_REPORT_ONLY:
    CONTENT_SECURITY_POLICY_REPORT_ONLY = {"DIRECTIVES": CSP_BASE_DIRECTIVES}
else:
    CONTENT_SECURITY_POLICY = {"DIRECTIVES": CSP_BASE_DIRECTIVES}


# ✅ v5: VAPID Push Notifications
# غيّر هذه القيم بالمفاتيح المولَّدة في .env
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "").replace("\\n", "\n")
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "").replace("\\n", "\n")
VAPID_PUBLIC_KEY_B64 = os.environ.get("VAPID_PUBLIC_KEY_B64", "")
VAPID_CLAIMS_EMAIL = os.environ.get("VAPID_CLAIMS_EMAIL", "")

# ✅ DPO — مسؤول حماية البيانات (PDPPL م.17)
# بياناتُ التواصل من البيئة وحدَها، والافتراضُ فارغ: المستودعُ عامّ، واسمُ شخصٍ
# وبريدُه وجوّالُه ليست إعداداتٍ تُودَع (انظر `.env.example`).
DPO_NAME = os.environ.get("DPO_NAME", "")
DPO_EMAIL = os.environ.get("DPO_EMAIL", "")
# مستلِمُ إشعارات «أرسل إلى المطوّر»: يُضبط على خدمة الويب؛ فارغٌ = لا إرسال (يُسجَّل فشلاً).
DEVELOPER_FEEDBACK_RECIPIENT = os.environ.get("DEVELOPER_FEEDBACK_RECIPIENT", "")
DPO_PHONE = os.environ.get("DPO_PHONE", "")

# ── الاحتفاظُ بالبيانات (PDPPL م.7 و10) ───────────────────────────────
# بعد كم يوماً يُحذف ما انقضى غرضُه من آثار التشغيل (السياسةُ جدولاً جدولاً في
# docs/privacy/data_retention.md، والمُنفِّذ governance/retention.py). كان المتغيّرُ
# معلَناً في .railway/railway.ts ولا يقرؤه أحد. والصفرُ يعطّل الحذفَ كلَّه.
#
# نصٌّ خامٌ لا `int()` هنا: الإعداداتُ تُقرأ عند إقلاع كلّ عمليّة، فخطأٌ مطبعيٌّ
# في البيئة كان يُسقط المنصّةَ كلَّها لا الحذفَ وحده — وقد وقع يومَ 2026-09-14:
# القيمةُ على Railway `730)` فسقطت مرحلةُ الإصدار مرّتين. والتحليلُ في
# `governance.retention.retention_days()`: ما لا يُفهم رقماً يعطّل الحذفَ ويُسجَّل خطأً.
PDPPL_DATA_RETENTION_DAYS = os.environ.get("PDPPL_DATA_RETENTION_DAYS", "730").strip()

# ── تجربةُ مطوّر المنصّة على أفعال المدير في تقييم الأداء (2026-09-19، بطلب المالك) ──
# مطوّرُ المنصّة (`is_superuser`) يرى شاشاتِ المدير للعرض دائماً. وهذا المفتاحُ يمنحه **الأفعالَ**
# أيضاً — اعتمادَ التقرير، وتدوينَ تاريخ الاستلام، وتدوينَ قرار لجنة التظلّم — لتجربتها. مؤقّتٌ
# بقرار المالك ("نجرّب ثمّ نسحب الصلاحيّة"): يُطفأ بإزالة المتغيّر من Railway بلا تعديل شيفرة.
# ومُطفأٌ افتراضاً، وكلُّ فعلٍ به يُسجَّل في AuditLog بعلامة `developer_trial`.
APPRAISAL_DEVELOPER_ACTS_AS_PRINCIPAL = config(
    "APPRAISAL_DEVELOPER_ACTS_AS_PRINCIPAL", default=False, cast=bool
)

# ══════════════════════════════════════════════════════════════════════
# ✅ v5.4: django-axes — حماية من هجمات القوة الغاشمة (Brute Force)
# ══════════════════════════════════════════════════════════════════════
# يقفل بعد 5 محاولات فاشلة لمدة 5 دقائق (قرار 2026-09-14 — كانت ساعة).
# يستخدم قاعدة البيانات لتتبع المحاولات (لا يحتاج Redis منفصلاً).
# ─────────────────────────────────────────────────────────────────────
# عدد المحاولات الفاشلة قبل القفل (OWASP: ≤ 10)
AXES_FAILURE_LIMIT = config("AXES_FAILURE_LIMIT", default=5, cast=int)

# مدّةُ القفل بالدقائق، وتساوي `LOCK_MINUTES` في core/views_auth.py — فلا يرى
# المقفولُ خمسَ دقائق من بابٍ وساعةً من الآخر. والمتغيّرُ القديمُ AXES_COOLOFF_TIME
# (بالساعات) لم يعد يُقرأ.
AXES_COOLOFF_TIME = timedelta(minutes=config("AXES_COOLOFF_MINUTES", default=5, cast=int))

# القفلُ على الحساب **من العنوان نفسه**. والقائمةُ المسطّحة ["username", "ip_address"]
# كانت تعني في axes «أيّهما» لا «كلاهما»: خمسُ محاولاتٍ خاطئةٍ من شبكة المدرسة أو
# من شبكة جوّالٍ يتشارك مشتركوها عنواناً واحداً كانت تقفل كلَّ من خلفه، ولو لم
# يخطئ. والرشُّ على حساباتٍ كثيرةٍ من عنوانٍ واحدٍ يحدّه `ratelimit` على باب الدخول
# (10 في الدقيقة لكلّ عنوان).
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]

# إعادة تعيين العداد عند تسجيل الدخول الناجح
AXES_RESET_ON_SUCCESS = True

# لا تسجّل الـ passwords في السجلات (أمان إضافي)
AXES_SENSITIVE_PARAMETERS = ["password"]

# لا سجلات زائدة في الإنتاج
AXES_VERBOSE = False

# الحقل المستخدم كـ "username" في هذا المشروع
# حقلُ النموذج، ومعه الدالّةُ التي تحوّله إلى مفتاحٍ معياريّ. وبلا الدالّة يقرأ
# axes ما كُتب خاماً فيحفظ الرقمَ الشخصيَّ نصّاً صريحاً في `axes_accessattempt`
# — بينما نشفّره في `CustomUser`. ولها أثرٌ ثانٍ: معرّفان لمستخدمٍ واحدٍ كانا
# سيعطيانه مفتاحَي قفلٍ اثنين، أي عشرَ محاولاتٍ لا خمساً.
AXES_USERNAME_FORM_FIELD = "identifier"
AXES_USERNAME_CALLABLE = "core.auth_identity.axes_username"

# إعادة توجيه مخصصة عند القفل — None = HTTP 403 الافتراضي
AXES_LOCKOUT_URL = None

# ── F-004: حد حجم الرفع (5 MB) — OWASP File Upload ──────────────
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5 MB

# ── [B4-2B] خطّ التسليم المتتبَّع — مُطفأ افتراضياً وفي الإنتاج ──────
#
# الاسم يذكر `HUB` عمداً: `NotificationHub` وحده يُنشئ واقعةً وتسليمات،
# ومنتجا Push المباشران خارج الـHub ما زالا legacy. اسمٌ عامّ كان سيدّعي
# تغطيةً لا يملكها.
#
# ودمجُ الكاتب ليس تفعيلاً له. التفعيل في الإنتاج يحتاج مُصالِحاً يلتقط
# التسليمات المعلّقة، ولم يُبنَ بعد (B4-4): الكاتب اليوم يُنتج صفوفاً قد تبقى
# `pending` حتى بعد وصول الرسالة، لأن آلة الحالات تنتظر B4-3.
NOTIFICATION_HUB_DELIVERY_PIPELINE_ENABLED = config(
    "NOTIFICATION_HUB_DELIVERY_PIPELINE_ENABLED",
    default=False,
    cast=bool,
)

# ── [B4-3A] مهلة استئجار التسليم ────────────────────────────────────
#
# إعداد مستقلّ عن راية الخطّ: المهلة تصف زمن التنفيذ لا تشغيله.
#
# خمس عشرة دقيقة قيمة محافظة عمداً وغير مضبوطة بقياس — لا قياس ممكن والراية
# مُطفأة. والاتّجاه مقصود: انقضاءٌ كاذب أخطر من مهلة طويلة، لأنه يجعل مُصالِحاً
# مستقبلياً يصنّف تنفيذاً حيّاً `unknown_outcome`، بينما المهلة الأطول تُؤخّر
# الاكتشاف وحده.
NOTIFICATION_DELIVERY_LEASE_SECONDS = config(
    "NOTIFICATION_DELIVERY_LEASE_SECONDS",
    default=900,
    cast=int,
)

if NOTIFICATION_DELIVERY_LEASE_SECONDS <= 0:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(
        "NOTIFICATION_DELIVERY_LEASE_SECONDS يجب أن تكون موجبة — "
        "مهلة صفرية أو سالبة تجعل كل استئجار منتهياً لحظة إنشائه."
    )

# ── [B4-PRE4] مهلة استئجار الطبر ────────────────────────────────────
#
# قصيرة عمداً: محاولة إدخال العمل إلى الوسيط عملٌ سريع، وانقضاء هذا الاستئجار
# **قابل للاستحواذ ثانيةً** خلافاً لاستئجار التسليم — فقدانُ العامل هنا لا يعني
# أن المزوّد استقبل شيئاً، وأسوأ ما يقع رسالةٌ مكرّرة في الوسيط يحتملها سياج
# التسليم.
NOTIFICATION_ENQUEUE_LEASE_SECONDS = config(
    "NOTIFICATION_ENQUEUE_LEASE_SECONDS",
    default=60,
    cast=int,
)

if NOTIFICATION_ENQUEUE_LEASE_SECONDS <= 0:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured("NOTIFICATION_ENQUEUE_LEASE_SECONDS يجب أن تكون موجبة")


# ── [B4-4] عتبات المُصالِح ───────────────────────────────────────────
#
# ثلاث عتبات لا واحدة، لأن ثلاثة أسئلة مختلفة تُطرح على الصفّ:
#
#   PENDING_GRACE     هل التسليم قديمٌ فعلاً؟ يُقاس بـ`status_changed_at`.
#   REQUEUE_INTERVAL  هل طُبر قريباً؟ يُقاس بـ`last_enqueue_attempt_at`.
#   RETRY_WAIT_GRACE  هل `retry_wait` يتيمة؟ عتبة محافظة عمداً.
#
# الأولى وحدها كانت ستُعيد الطبر بعد كل فشل مباشرةً — التسليم لم ينتقل فيبدو
# قديماً أبداً. والثانية وحدها كانت ستلتقط صفّاً طُبر قبل ثانية ولم يصل العامل
# إليه بعد.
NOTIFICATION_PENDING_GRACE_SECONDS = config(
    "NOTIFICATION_PENDING_GRACE_SECONDS", default=600, cast=int
)

NOTIFICATION_REQUEUE_INTERVAL_SECONDS = config(
    "NOTIFICATION_REQUEUE_INTERVAL_SECONDS", default=900, cast=int
)

# أطول من الأولى عمداً: `retry_wait` تعني أن العامل قرّر الإعادة وجدولها، فقد
# تكون المهمة المؤجَّلة ما تزال في الوسيط تنتظر موعدها. عتبةٌ قصيرة هنا تُنتج
# تنفيذين لنفس التسليم — أحدهما من إعادة Celery والآخر من المُصالِح — ولا يمنع
# التكرار عند المزوّد إلا سباقُهما على الاستحواذ.
NOTIFICATION_RETRY_WAIT_GRACE_SECONDS = config(
    "NOTIFICATION_RETRY_WAIT_GRACE_SECONDS", default=1800, cast=int
)

# ميزانية المحاولات الدائمة لكل تسليم.
#
# `max_retries=3` على مهامّ القنوات يعني أربع محاولات داخل رسالة واحدة، فهذه
# القيمة تُطابقها — لكن المرجع الآن هو الصفّ لا الرسالة: رسالةٌ جديدة يُنشئها
# المُصالِح تبدأ من `request.retries = 0` بينما `attempt_count` يُكمل من حيث
# انتهى.
NOTIFICATION_MAX_DELIVERY_ATTEMPTS = config(
    "NOTIFICATION_MAX_DELIVERY_ATTEMPTS", default=4, cast=int
)

#: سقفُ ما يُعالَج في نداء واحد — المُصالِح مدرسةٌ واحدة لكل استدعاء.
NOTIFICATION_RECONCILER_BATCH_SIZE = config(
    "NOTIFICATION_RECONCILER_BATCH_SIZE", default=200, cast=int
)

for _name in (
    "NOTIFICATION_PENDING_GRACE_SECONDS",
    "NOTIFICATION_REQUEUE_INTERVAL_SECONDS",
    "NOTIFICATION_RETRY_WAIT_GRACE_SECONDS",
    "NOTIFICATION_RECONCILER_BATCH_SIZE",
    "NOTIFICATION_MAX_DELIVERY_ATTEMPTS",
):
    if locals()[_name] <= 0:
        from django.core.exceptions import ImproperlyConfigured

        raise ImproperlyConfigured(f"{_name} يجب أن تكون موجبة")


# ── [B4-5] ميزانية زمن Push — حدٌّ بنيويّ لا رقمٌ مُختار ─────────────
#
# `webpush()` يمرّر `timeout` إلى `requests`، وبلا تمريره لا مهلة إطلاقاً:
# اتصالٌ واحد يبتلع الحزم يُعلّق المهمّة بلا حدّ. وحينها ينقضي استئجار التسليم
# والعامل حيٌّ يعمل، فيكتب المُصالِح `unknown_outcome` على تسليمٍ لم يُحسم بعد —
# ثم يعود العامل فيجد سياجه ساقطاً فلا يكتب شيئاً. فنخسر نتيجةً كانت **معروفة**
# ونُسجّل جهلاً لم يكن قائماً، وهي نهايةٌ لا تُسترَدّ بالأتمتة.
#
# ورفعُ مدّة الاستئجار لا يُصلح ذلك بل يؤجّله: العلّة أن الحدّ الأعلى للتنفيذ
# **غير معرَّف** بينما الاستئجار يفترض أنه معرَّف.
PUSH_PROVIDER_TIMEOUT_SECONDS = config("PUSH_PROVIDER_TIMEOUT_SECONDS", default=10, cast=float)

#: سقفٌ **مفروض** لا مقيس. القياس اليوم صفر ولا يحمي الغد: لو صار لمستخدم
#: عشرون اشتراكاً فعّالاً انكسرت متباينة الميزانية صامتةً. والسقف يجعل أسوأ حالة
#: قابلة للحساب سلفاً — وهو ما يجعل هذا العقد عقداً لا تقديراً.
PUSH_MAX_ACTIVE_SUBSCRIPTIONS = config("PUSH_MAX_ACTIVE_SUBSCRIPTIONS", default=4, cast=int)

#: ما لا يُغطّيه `timeout` المزوّد: DNS وTLS والتشفير وثلاث كتابات قاعدة لكل
#: اشتراك والانتقال بينها. مهلةُ `requests` مهلةُ انتظارٍ على الاتصال والقراءة
#: لا سقفٌ إجماليّ لزمن العملية، فحسابُ الميزانية بها وحدها يُنتج رقماً أصغر من
#: الواقع. القيمة تُقاس محلياً ثم تُختار فوق القياس بهامش.
PUSH_PER_SUBSCRIPTION_OVERHEAD_SECONDS = config(
    "PUSH_PER_SUBSCRIPTION_OVERHEAD_SECONDS", default=5, cast=float
)

#: كلفةٌ ثابتة لا تتكرّر مع الاشتراكات: حلّ التسليم، والاستحواذ، وبناء الحمولة.
PUSH_TASK_MARGIN_SECONDS = config("PUSH_TASK_MARGIN_SECONDS", default=15, cast=float)

#: المهلة اللينة — تُرفع كاستثناء **داخل** المسار المالك للاستئجار، فيكتب العامل
#: نهايته بنفسه بدل أن يتركها للمُصالِح.
PUSH_SOFT_TIME_LIMIT_SECONDS = config("PUSH_SOFT_TIME_LIMIT_SECONDS", default=120, cast=int)

#: الفارق الواجب بين المهلة اللينة وانقضاء الاستئجار: زمنُ رفع الاستثناء وكتابة
#: النهاية المُسيَّجة. بدونه قد تقع المهلة وينقضي الاستئجار في اللحظة نفسها.
PUSH_LEASE_SAFETY_MARGIN_SECONDS = config(
    "PUSH_LEASE_SAFETY_MARGIN_SECONDS", default=60, cast=float
)

#: أسوأ حالةٍ محسوبة — لا مقيسة. تُشتقّ من السقف والمهل، فتبقى صادقة مهما تغيّر
#: سلوك الشبكة.
PUSH_WORST_CASE_BUDGET_SECONDS = (
    PUSH_MAX_ACTIVE_SUBSCRIPTIONS
    * (PUSH_PROVIDER_TIMEOUT_SECONDS + PUSH_PER_SUBSCRIPTION_OVERHEAD_SECONDS)
    + PUSH_TASK_MARGIN_SECONDS
)


def _validate_push_budget() -> None:
    """يرفض الإقلاع إن اختلّت سلسلة الحدود.

    الترتيب الواجب:

        أسوأ حالة  <  المهلة اللينة  <  ( الاستئجار − هامش الأمان )

    وكسرُها لا ينكشف في الاختبارات بل في الإنتاج على هيئة `unknown_outcome`
    متفرّقة لا يعرف أحد سببها — فيُفحص هنا حيث يُقرأ الإعداد، لا حيث يُستعمل.
    """
    from django.core.exceptions import ImproperlyConfigured

    # كلُّ حدٍّ يدخل الحساب يجب أن يكون موجباً — وحدّان منها كانا خارج الفحص:
    # `overhead` و`margin` يدخلان **جمعاً** في أسوأ حالة، فقيمةٌ سالبة فيهما
    # تُقلّصها فتمرّ المتباينة كذباً. وذلك أسوأ من غياب الفحص: حارسٌ يشهد بأن
    # الميزانية سليمة وهي ليست كذلك.
    positives = {
        "PUSH_PROVIDER_TIMEOUT_SECONDS": PUSH_PROVIDER_TIMEOUT_SECONDS,
        "PUSH_MAX_ACTIVE_SUBSCRIPTIONS": PUSH_MAX_ACTIVE_SUBSCRIPTIONS,
        "PUSH_PER_SUBSCRIPTION_OVERHEAD_SECONDS": PUSH_PER_SUBSCRIPTION_OVERHEAD_SECONDS,
        "PUSH_TASK_MARGIN_SECONDS": PUSH_TASK_MARGIN_SECONDS,
        "PUSH_SOFT_TIME_LIMIT_SECONDS": PUSH_SOFT_TIME_LIMIT_SECONDS,
        "PUSH_LEASE_SAFETY_MARGIN_SECONDS": PUSH_LEASE_SAFETY_MARGIN_SECONDS,
    }

    for name, value in positives.items():
        if value <= 0:
            raise ImproperlyConfigured(f"{name} يجب أن تكون موجبة — {value}")

    if PUSH_WORST_CASE_BUDGET_SECONDS >= PUSH_SOFT_TIME_LIMIT_SECONDS:
        raise ImproperlyConfigured(
            "ميزانية أسوأ حالة لـPush "
            f"({PUSH_WORST_CASE_BUDGET_SECONDS:.0f}s) تبلغ المهلة اللينة "
            f"({PUSH_SOFT_TIME_LIMIT_SECONDS}s) أو تتجاوزها — "
            "فقد تُقطع المهمّة قبل أن تُكمل عملاً مشروعاً"
        )

    ceiling = NOTIFICATION_DELIVERY_LEASE_SECONDS - PUSH_LEASE_SAFETY_MARGIN_SECONDS

    if PUSH_SOFT_TIME_LIMIT_SECONDS >= ceiling:
        raise ImproperlyConfigured(
            f"المهلة اللينة ({PUSH_SOFT_TIME_LIMIT_SECONDS}s) لا تترك هامشاً قبل "
            f"انقضاء الاستئجار ({NOTIFICATION_DELIVERY_LEASE_SECONDS}s − "
            f"{PUSH_LEASE_SAFETY_MARGIN_SECONDS:.0f}s = {ceiling:.0f}s) — "
            "فقد ينقضي الاستئجار قبل أن يكتب العامل نهايته"
        )


_validate_push_budget()

# ── الجدولة الذكيّة ──
#: ميزانيةُ زمن التوليد بالثواني: محاولاتٌ متعاقبةٌ حتّى تنفد (3 على الأقلّ، 20 على الأكثر).
SCHEDULE_TIME_BUDGET_SECONDS = int(os.environ.get("SCHEDULE_TIME_BUDGET_SECONDS", "60"))

# ── عنوانُ العميل خلف وكيل ─────────────────────────────────────────────
# كم قفزةً موثوقةً تُلحقها البنيةُ بآخر X-Forwarded-For. محلّياً لا وكيلَ فالترويسة
# لا تُصدَّق (0)؛ Railway يُلحق قفزةً واحدة (الإنتاج 1). راجع core/request_utils.py.
TRUSTED_PROXY_HOPS = int(os.environ.get("TRUSTED_PROXY_HOPS", "0"))

# والحدُّ على باب الدخول وقفلُ axes يعدّان بهذا العنوان نفسه (P1-2). كانا يقرآن
# REMOTE_ADDR، وهو على Railway عنوانُ الوكيل الداخليّ: كلُّ ما سجّله axes على
# الإنتاج عناوينُ داخليّة (فحص 2026-09-16). فكان «عشرُ محاولاتٍ في الدقيقة لكلّ
# عنوان» عشراً للمدرسة كلّها، ومخطئٌ واحدٌ يحبس الجميع.
RATELIMIT_IP_META_KEY = "core.request_utils.get_client_ip"
AXES_CLIENT_IP_CALLABLE = "core.request_utils.get_client_ip"

# سقوطُ Redis كان يُسقط `@ratelimit` بخطأٍ غيرِ مُلتقَط (500) على كلّ عرضٍ
# يحمله — لا حدّاً مرفوضاً. والقفلُ الحقيقيّ على باب الدخول عند axes، وهو
# يُخزَّن في القاعدة لا في Redis (`AxesDatabaseHandler` الافتراضيّ) فيبقى
# عاملاً كاملاً وقت الانقطاع. فالتعادُل هنا آمنٌ: يفتح `@ratelimit` وحده.
#
# هذا الإعداد وحده لا يكفي: `django_ratelimit.core.get_usage` يلتقط
# `socket.gaierror` فقط حول `cache.add()`، فاستثناء Redis الحقيقيّ يفلت قبل
# أن يصل الفرعَ الذي يقرأ هذا الإعداد. الإصلاحُ الفعليّ في
# `core/ratelimit_safe.py` (يستعمله `core/views_auth.py` وoperations/api_views.py
# بدل `django_ratelimit.decorators.ratelimit` مباشرة)، وهذا الإعداد دفاعٌ ثانٍ
# للفرع الذي تغطّيه المكتبة فعلاً (قيمةٌ فارغة بلا استثناء).
RATELIMIT_FAIL_OPEN = True

# ── كم نسخةً سابقةً من الجدول تُبقى ────────────────────────────────────
# كلُّ اعتمادٍ يُؤرشف الجدولَ السابق كاملاً — 870 صفّاً مطفأً — ولا يحذفه، فبلغت
# النسخُ المؤرشفة خمساً في يومٍ واحد (2026-09-05). قرارُ المدرسة يومَها: **جدولٌ
# واحدٌ فقط، الحيّ**. فما يُؤرشف يذهب مع حصصه عند الاعتماد التالي، والمسودّاتُ
# باقيةٌ لأنّها عملٌ جارٍ لا نسخةٌ قديمة.
SCHEDULE_ARCHIVE_RETENTION = int(os.environ.get("SCHEDULE_ARCHIVE_RETENTION", "0"))

# ── محرّكُ الحكم الواحد (`assessments/verdict_engine.py`) ─────────────────
# مطفأٌ افتراضاً: ما دام كذلك يبقى حسابُ الدرجات على حاله القديم، فلا تتغيّر شهادةٌ ولا
# نتيجة. تُرفع مع الطلب الذي يحوّل المستهلكين لقراءة الحكم المخزَّن — والحالاتُ الجديدة
# («مُرفَّع»، «دور ثانٍ»…) لا تفهمها الشاشاتُ التي تعدّ `fail` و`pass` وحدَهما. والمتغيّرُ
# يُضبط على الخدمات الثلاث (ويب + worker + beat) معاً.
VERDICT_ENGINE_ENABLED = os.environ.get("VERDICT_ENGINE_ENABLED", "").strip().lower() in {
    "1",
    "true",
    "yes",
}
