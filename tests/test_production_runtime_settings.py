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
    "USE_S3": "false",
}

_RUNTIME_KEYS = (
    "REDIS_URL",
    "CELERY_ASYNC_ENABLED",
    "USE_REDIS_SESSIONS",
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
