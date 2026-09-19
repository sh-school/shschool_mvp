"""Regression tests for production Redis/Celery/session runtime policy."""

import os
import subprocess
import sys

_REQUIRED_ENV = {
    "DEBUG": "false",
    "SECRET_KEY": "test-only-secret-key-for-production-settings-regression",
    "FERNET_KEY": "dGVzdC1mZXJuZXQta2V5LTMyLWJ5dGVzLWZvcmNpLS0=",
    "EXCEL_PROTECTION_PASSWORD": "test-only-password",
    "ALLOWED_HOSTS": "localhost",
    "SENTRY_DSN": "",
    # S3 إلزاميٌّ في الإنتاج الآن (البند 11) — بلا هذه الثلاث يفشل كلّ اختبارٍ
    # هنا عند الاستيراد (ImproperlyConfigured)، لا فحصَ الإعداد الذي يقصده.
    "AWS_ACCESS_KEY_ID": "test-only-access-key",
    "AWS_SECRET_ACCESS_KEY": "test-only-secret-key",  # pragma: allowlist secret
    "AWS_STORAGE_BUCKET_NAME": "test-only-bucket",
    # فارغةٌ عمداً — قيمٌ صريحةٌ لا غياب: decouple يقرأ os.environ أوّلاً ثمّ
    # ملفّ .env الحقيقيّ في هذه الشجرة (قد يحمل مفاتيح R2 فعليّة، البند 11)؛
    # فبلا هذا الحضور الصريح يتسرّب محتوى الملفّ الحقيقيّ إلى العملية الفرعية
    # رغم `env=` الممرَّر لها — الغيابُ من القاموس ليس غياباً من decouple.
    "AWS_S3_ENDPOINT_URL": "",
    "AWS_S3_REGION_NAME": "me-south-1",
    "AWS_S3_CUSTOM_DOMAIN": "",
}

_RUNTIME_KEYS = (
    "REDIS_URL",
    "CELERY_ASYNC_ENABLED",
    "USE_REDIS_SESSIONS",
    # [CORS] يُنزع كي يُختبر **غياب** الإعداد لا ما يصادف وجوده في البيئة.
    "CORS_ALLOWED_ORIGINS",
)


def _load_production_settings(**overrides):
    env = os.environ.copy()

    for key in _RUNTIME_KEYS:
        env.pop(key, None)

    env.update(_REQUIRED_ENV)
    env.update({key: str(value) for key, value in overrides.items()})

    code = r"""
import shschool.settings.production as settings

print("CACHE_BACKEND=" + settings.CACHES["default"]["BACKEND"])
print("SESSION_ENGINE=" + settings.SESSION_ENGINE)
print("CELERY_EAGER=" + str(settings.CELERY_TASK_ALWAYS_EAGER))
print("CELERY_PROPAGATES=" + str(settings.CELERY_TASK_EAGER_PROPAGATES))
print("CELERY_BROKER=" + str(getattr(settings, "CELERY_BROKER_URL", "")))
print("CORS=" + "|".join(settings.CORS_ALLOWED_ORIGINS))
print("CONN_MAX_AGE=" + str(settings.DATABASES["default"]["CONN_MAX_AGE"]))
print("DB_OPTIONS=" + str(settings.DATABASES["default"].get("OPTIONS", {})))
print("STORAGE_BACKEND=" + settings.STORAGES["default"]["BACKEND"])
print("MEDIA_URL=" + settings.MEDIA_URL)
"""

    return subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        cwd=os.getcwd(),
        capture_output=True,
        text=True,
        check=False,
    )


def _values(result):
    values = {}

    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value

    return values


def test_redis_does_not_enable_async_celery_or_cache_sessions():
    redis_url = "redis://example.invalid:6379/0"

    result = _load_production_settings(REDIS_URL=redis_url)

    assert result.returncode == 0, result.stderr

    values = _values(result)

    assert values["CACHE_BACKEND"] == "django.core.cache.backends.redis.RedisCache"
    assert values["SESSION_ENGINE"] == "django.contrib.sessions.backends.db"
    assert values["CELERY_EAGER"] == "True"
    assert values["CELERY_PROPAGATES"] == "False"
    assert values["CELERY_BROKER"] == redis_url


def test_celery_async_requires_explicit_opt_in():
    redis_url = "redis://example.invalid:6379/0"

    result = _load_production_settings(
        REDIS_URL=redis_url,
        CELERY_ASYNC_ENABLED="true",
    )

    assert result.returncode == 0, result.stderr

    values = _values(result)

    assert values["CELERY_EAGER"] == "False"
    assert values["CELERY_BROKER"] == redis_url


def test_celery_async_without_redis_fails_closed():
    result = _load_production_settings(
        CELERY_ASYNC_ENABLED="true",
    )

    assert result.returncode != 0
    assert "CELERY_ASYNC_ENABLED=true requires REDIS_URL" in result.stderr


def test_redis_sessions_without_redis_fail_closed():
    result = _load_production_settings(
        USE_REDIS_SESSIONS="true",
    )

    assert result.returncode != 0
    assert "USE_REDIS_SESSIONS=true requires REDIS_URL" in result.stderr


def test_redis_sessions_are_separate_opt_in():
    redis_url = "redis://example.invalid:6379/0"

    result = _load_production_settings(
        REDIS_URL=redis_url,
        USE_REDIS_SESSIONS="true",
    )

    assert result.returncode == 0, result.stderr

    values = _values(result)

    assert values["SESSION_ENGINE"] == "django.contrib.sessions.backends.cache"
    assert values["CELERY_EAGER"] == "True"
    assert values["CELERY_PROPAGATES"] == "False"


# ══════════════════════════════════════════════════════════════════
#  CORS في الإنتاج — الفشل مغلق لا محذَّر
# ══════════════════════════════════════════════════════════════════
#
# `base.py` يقرأ `CORS_ALLOWED_ORIGINS` بافتراض `localhost:3000,localhost:8000`
# — صالحٌ للتطوير. وكان الإنتاج يرثه ويكتفي بتحذير، **والتحذير لا يُغلق باباً**:
# مع `CORS_ALLOW_CREDENTIALS = True` تستطيع صفحةٌ على `localhost` قراءة
# استجابات الـAPI بجلسة مستخدمٍ مسجَّل.


def _cors(result):
    raw = _values(result)["CORS"]
    return raw.split("|") if raw else []


def test_absent_cors_configuration_allows_no_origin():
    """غيابُ الإعداد يعني «لا أصل» لا «أصول التطوير»."""
    result = _load_production_settings()

    assert result.returncode == 0, result.stderr
    assert _cors(result) == []


def test_an_explicit_https_origin_is_preserved():
    """الإصلاح يُقصي المحلّيّ ولا يُفرغ ما ضُبط عمداً."""
    result = _load_production_settings(CORS_ALLOWED_ORIGINS="https://frontend.example")

    assert result.returncode == 0, result.stderr
    assert _cors(result) == ["https://frontend.example"]


def test_several_https_origins_keep_their_order():
    result = _load_production_settings(CORS_ALLOWED_ORIGINS="https://a.example,https://b.example")

    assert _cors(result) == ["https://a.example", "https://b.example"]


def test_localhost_never_reaches_production_cors():
    """حتى حين يُضبط صراحةً — الخطأ يُقصى لا يُنفَّذ."""
    result = _load_production_settings(CORS_ALLOWED_ORIGINS="http://localhost:3000")

    assert result.returncode == 0, result.stderr
    assert _cors(result) == []


def test_loopback_address_never_reaches_production_cors():
    """`127.0.0.1` هو `localhost` بعنوانٍ آخر — والحارس يعرف الاثنين."""
    result = _load_production_settings(CORS_ALLOWED_ORIGINS="http://127.0.0.1:8000")

    assert _cors(result) == []


def test_a_mixed_list_keeps_the_valid_and_drops_the_local():
    """الحالة الواقعية: إعدادٌ صحيح تسلّل إليه أصلٌ محلّيّ."""
    result = _load_production_settings(
        CORS_ALLOWED_ORIGINS="https://valid.example,http://localhost:3000"
    )

    assert _cors(result) == ["https://valid.example"]


def test_the_development_default_is_untouched():
    """`base.py` يبقى كما هو — الإصلاح إنتاجيّ لا عامّ.

    وحارسٌ ضدّ إصلاحٍ يبدو أشمل: نزعُ الافتراض من `base` كان سيكسر التطوير
    المحلّيّ وstaging معاً، وكلاهما يحتاجه عمداً.
    """
    import pathlib

    base = pathlib.Path("shschool/settings/base.py").read_text(encoding="utf-8")

    assert 'default="http://localhost:3000,http://localhost:8000"' in base


# ══════════════════════════════════════════════════════════════════
#  اتّصالُ القاعدة تحت ASGI — بلا استمرار (P4-9)
# ══════════════════════════════════════════════════════════════════


def test_connections_are_not_kept_alive_under_asgi():
    """daphne يخدم على مسبح خيوطٍ واحد؛ اتّصالٌ مستمرٌّ قد يعود لخيطٍ غير الذي فتحه."""
    result = _load_production_settings()

    assert result.returncode == 0, result.stderr
    assert _values(result)["CONN_MAX_AGE"] == "0"


def test_the_environment_variable_cannot_override_it():
    """`DB_CONN_MAX_AGE` قرارٌ معماريٌّ لهذا الخادم — لا رايةٌ تُضبط بالخطأ."""
    result = _load_production_settings(DB_CONN_MAX_AGE="600")

    assert result.returncode == 0, result.stderr
    assert _values(result)["CONN_MAX_AGE"] == "0"


# ══════════════════════════════════════════════════════════════════
#  statement_timeout — علمٌ صريح من البيئة، لا استنتاجٌ من العملية (البند 6)
# ══════════════════════════════════════════════════════════════════


def test_statement_timeout_is_disabled_by_default():
    """معطَّلٌ افتراضياً — يُفعَّل فقط بضبط الراية صراحةً على خدمة الويب في Railway.

    لا فحص `sys.argv`/اسم العملية هنا: `test_sentry_error_only_mode.py` يفحص
    `production.py` بشجرة AST ويُسقط أيّ استخدامٍ لـ`sys.argv` فيه — اكتشافٌ
    ضمنيّ للعملية يكسر بصمت.
    """
    result = _load_production_settings()

    assert result.returncode == 0, result.stderr
    assert _values(result)["DB_OPTIONS"] == "{}"


def test_statement_timeout_is_configurable():
    result = _load_production_settings(DB_STATEMENT_TIMEOUT_MS="5000")

    assert result.returncode == 0, result.stderr
    assert "statement_timeout=5000" in _values(result)["DB_OPTIONS"]


def test_a_zero_timeout_keeps_it_disabled():
    result = _load_production_settings(DB_STATEMENT_TIMEOUT_MS="0")

    assert result.returncode == 0, result.stderr
    assert _values(result)["DB_OPTIONS"] == "{}"


# ══════════════════════════════════════════════════════════════════
#  S3 إلزاميٌّ في الإنتاج — لا تراجعَ صامتاً إلى القاعدة (البند 11)
# ══════════════════════════════════════════════════════════════════


def test_s3_is_wired_as_the_default_storage_when_configured():
    result = _load_production_settings()

    assert result.returncode == 0, result.stderr
    values = _values(result)
    assert values["STORAGE_BACKEND"] == "storages.backends.s3boto3.S3Boto3Storage"


def test_missing_access_key_fails_the_boot_instead_of_falling_back():
    """كانت هذه الحالة تُصدر تحذيراً وتتراجع إلى DatabaseStorage — الآن تُسقط الإقلاع."""
    result = _load_production_settings(AWS_ACCESS_KEY_ID="")

    assert result.returncode != 0
    assert "AWS_ACCESS_KEY_ID" in result.stderr


def test_missing_bucket_name_fails_the_boot():
    result = _load_production_settings(AWS_STORAGE_BUCKET_NAME="")

    assert result.returncode != 0
    assert "AWS_STORAGE_BUCKET_NAME" in result.stderr


def test_an_s3_compatible_endpoint_shapes_the_media_url():
    """R2/MinIO: الرابطُ يُبنى من نقطة النهاية لا من نمط AWS القياسيّ."""
    result = _load_production_settings(
        AWS_S3_ENDPOINT_URL="https://example.r2.cloudflarestorage.com"
    )

    assert result.returncode == 0, result.stderr
    assert (
        _values(result)["MEDIA_URL"]
        == "https://example.r2.cloudflarestorage.com/test-only-bucket/media/"
    )


def test_the_aws_default_media_url_is_used_without_an_endpoint():
    result = _load_production_settings()

    assert result.returncode == 0, result.stderr
    assert (
        _values(result)["MEDIA_URL"]
        == "https://test-only-bucket.s3.me-south-1.amazonaws.com/media/"
    )
