"""
shschool/settings/staging.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Staging environment — mirrors production with relaxed strictness for QA testing.

Purpose:
  - Pre-production validation environment
  - Same infrastructure as production (Postgres, Redis, Sentry)
  - Slightly relaxed security to allow QA tools and debugging
  - Separate Sentry environment for clean error tracking

Usage:
  DJANGO_SETTINGS_MODULE=shschool.settings.staging
"""

from .production import *  # noqa: F401,F403

# ── Override: Staging-specific ─────────────────────────────────

DEBUG = False  # Keep False — staging must behave like production

ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS", default="staging.schoolos.qa,staging-schoolos.up.railway.app"
).split(",")

# ── Sentry: separate environment ──────────────────────────────
SENTRY_DSN = config("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            RedisIntegration(),
        ],
        traces_sample_rate=0.3,  # Higher sampling in staging for better debugging
        send_default_pii=False,  # PDPPL: no student PII even in staging
        environment="staging",
        release=config("APP_VERSION", default=f"v{PLATFORM_VERSION}"),
    )

SENTRY_ENVIRONMENT = "staging"

# ── SSL: relaxed for staging ──────────────────────────────────
# Staging may run behind different proxies; keep SSL redirect but relax HSTS
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
SECURE_HSTS_SECONDS = 3600  # 1 hour instead of 1 year — safe for testing
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False  # Never preload staging domains

# Exempt health endpoints from SSL redirect
SECURE_REDIRECT_EXEMPT = [r"^health/$", r"^ready/$", r"^status/$"]

# ── Sessions: shorter for testing ─────────────────────────────
SESSION_COOKIE_AGE = 7200  # 2 hours — more generous for QA sessions

# ── CSP: Report-Only in staging ───────────────────────────────
# Allows QA to test without CSP blocking new features
CSP_REPORT_ONLY = True

# ── Logging: more verbose for debugging ───────────────────────
LOGGING["root"]["level"] = "INFO"
LOGGING["loggers"]["django"]["level"] = "INFO"
LOGGING["loggers"]["django.request"]["level"] = "INFO"

# ── Email: never send real emails from staging ────────────────
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ── CORS: allow staging frontend ─────────────────────────────
_staging_cors = config(
    "CORS_ALLOWED_ORIGINS",
    default="https://staging.schoolos.qa,http://localhost:3000",
).split(",")
CORS_ALLOWED_ORIGINS = [o.strip() for o in _staging_cors if o.strip()]

# ── Axes: more lenient for QA testing ─────────────────────────
AXES_FAILURE_LIMIT = 20  # QA testers may trigger lockouts frequently
AXES_COOLOFF_TIME = 0.1  # 6 minutes cooloff instead of 1 hour

# ── ALLOWED_HOSTS validation (override production's strict check) ──
# Production raises ImproperlyConfigured if ALLOWED_HOSTS is empty.
# In staging we already set a default above, but suppress the production
# check by ensuring the list is never empty at this point.
if not ALLOWED_HOSTS or ALLOWED_HOSTS == [""]:
    ALLOWED_HOSTS = ["staging.schoolos.qa"]
