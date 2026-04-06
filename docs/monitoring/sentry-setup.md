# Sentry Error Monitoring — SchoolOS

## 1. Create Sentry Project

1. Go to [sentry.io](https://sentry.io) and create an account (or use self-hosted).
2. Create a new project:
   - Platform: **Django**
   - Project name: `schoolos-production`
   - Team: assign to your ops team
3. Copy the **DSN** from Project Settings > Client Keys (DSN).
   - Format: `https://<key>@o<org-id>.ingest.sentry.io/<project-id>`

## 2. Set Environment Variables on Railway

```bash
# Required — Sentry will NOT initialize without this
railway variables set SENTRY_DSN="https://<key>@o<org-id>.ingest.sentry.io/<project-id>"

# Optional — defaults to "production" if not set
railway variables set RAILWAY_ENVIRONMENT="production"

# Optional — defaults to PLATFORM_VERSION from base.py
railway variables set APP_VERSION="v5.4"
```

If `SENTRY_DSN` is not set or empty, Sentry will not initialize and the app will run normally without error monitoring. This is by design to avoid crashes in environments that don't need Sentry.

## 3. What Errors Are Captured

Sentry automatically captures:

- **Unhandled exceptions** in Django views (500 errors)
- **Unhandled Celery task failures** (via CeleryIntegration)
- **Redis connection errors** (via RedisIntegration)
- **Slow database queries** and N+1 detection (via DjangoIntegration)
- **JavaScript errors** if the Sentry browser SDK is added to templates (not included yet)
- **Performance traces** at 10% sample rate (`traces_sample_rate=0.1`)
- **Profiling data** at 10% sample rate (`profiles_sample_rate=0.1`)

### What Is NOT Captured

- `Http404` exceptions (filtered by default)
- `PermissionDenied` (403) — filtered by default
- `SuspiciousOperation` — filtered by default

## 4. Configuring Alerts

In Sentry UI:

1. **Alerts > Create Alert Rule**
2. Recommended alert rules for SchoolOS:
   - **High error volume**: > 50 events in 1 hour (critical)
   - **New issue**: first occurrence of a new error type (warning)
   - **Celery task failures**: filter by `celery` tag (critical)
   - **Slow transactions**: p95 response time > 2s (warning)
3. Set notification channels:
   - Email to the ops team
   - Slack webhook (if configured)
   - PagerDuty (for critical production alerts)

### Recommended Issue Grouping

- Go to Project Settings > Issue Grouping
- Use **default fingerprinting** — Sentry groups by stack trace automatically
- Add custom fingerprint for known noisy errors if needed

## 5. PDPPL Compliance — No PII Sent

SchoolOS handles student data protected under Qatar's **Personal Data Privacy Protection Law (PDPPL)**. The Sentry configuration enforces:

```python
send_default_pii=False  # Mandatory — do not change
```

This means Sentry will **NOT** collect:
- User IP addresses
- User session cookies
- HTTP request body data
- User email/name from `request.user`
- Form submission data

### Additional Recommendations

1. **Do not** enable Sentry's Session Replay feature (records user screens).
2. **Do not** set `send_default_pii=True` — this would violate PDPPL Article 13.
3. If you need user context for debugging, use anonymized IDs only:
   ```python
   # Example: in a middleware or signal
   from sentry_sdk import set_user
   set_user({"id": str(request.user.pk)})  # PK only, no name/email
   ```
4. Review Sentry's data scrubbing settings:
   - Project Settings > Security & Privacy > Data Scrubbing
   - Enable "Scrub data" and "Scrub IP addresses"
   - Add custom scrubbing rules for `national_id`, `phone`, `email` fields

## 6. Configuration Reference

The Sentry init block is in `shschool/settings/production.py`:

| Parameter | Value | Notes |
|-----------|-------|-------|
| `dsn` | `SENTRY_DSN` env var | Required to enable |
| `traces_sample_rate` | `0.1` (10%) | Performance monitoring |
| `profiles_sample_rate` | `0.1` (10%) | Code profiling |
| `send_default_pii` | `False` | PDPPL compliance |
| `environment` | `RAILWAY_ENVIRONMENT` or `"production"` | Filters in Sentry UI |
| `release` | `APP_VERSION` or `PLATFORM_VERSION` | Track deploys |
| Integrations | Django, Celery, Redis | Auto-instrumented |
