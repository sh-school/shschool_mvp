# Structured JSON Logging for SchoolOS

> How to implement structured JSON logging in Django for Railway log aggregation, Sentry correlation, and PDPPL compliance.

## Current State

SchoolOS production logging (`shschool/settings/production.py`) currently uses:

- **Text-based formatters** (`verbose` and `security`)
- **RotatingFileHandler** for file-based logs
- **StreamHandler** for console output (captured by Railway)
- **PIIMaskingFilter** (`core.logging_filters.PIIMaskingFilter`) on all handlers

The text format works but makes it difficult to search, filter, and aggregate logs in Railway's log explorer. Structured JSON logging enables machine-parseable log entries.

---

## Step 1: Install python-json-logger

```bash
pip install python-json-logger
pip freeze | grep json-logger >> requirements/production.txt
```

Or add to `requirements/production.txt`:

```
python-json-logger>=3.0.0,<4.0
```

---

## Step 2: Configure JSON Formatter

Update the `LOGGING` dict in `shschool/settings/production.py`:

```python
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        # Keep verbose for file handlers (human-readable)
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "security": {
            "format": "SECURITY {levelname} {asctime} {module} {message}",
            "style": "{",
        },
        # NEW: Structured JSON for Railway console
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
            "rename_fields": {
                "asctime": "timestamp",
                "name": "logger",
                "levelname": "level",
            },
            "static_fields": {
                "service": "schoolos",
                "environment": "production",
            },
            "timestamp": True,
        },
    },
    "filters": {
        "pii_masking": {
            "()": "core.logging_filters.PIIMaskingFilter",
        },
        # NEW: Add Sentry trace context to log entries
        "sentry_context": {
            "()": "core.logging_filters.SentryTraceFilter",
        },
    },
    "handlers": {
        "file": {
            "level": "WARNING",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs/django.log",
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "encoding": "utf-8",
            "formatter": "verbose",
            "filters": ["pii_masking"],
        },
        "security_file": {
            "level": "WARNING",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs/security.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 10,
            "encoding": "utf-8",
            "formatter": "security",
            "filters": ["pii_masking"],
        },
        # UPDATED: Console handler now uses JSON formatter
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["pii_masking", "sentry_context"],
        },
    },
    "root": {"handlers": ["file", "console"], "level": "WARNING"},
    "loggers": {
        "django": {"handlers": ["file", "console"], "level": "WARNING", "propagate": False},
        "django.security": {"handlers": ["security_file", "console"], "level": "WARNING", "propagate": False},
        "django.request": {"handlers": ["file", "console"], "level": "WARNING", "propagate": False},
        "notifications": {"handlers": ["file", "console"], "level": "INFO", "propagate": False},
        "notifications.hub": {"handlers": ["file", "console"], "level": "INFO", "propagate": False},
        "celery": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "core": {"handlers": ["security_file", "console"], "level": "WARNING", "propagate": False},
        "channels": {"handlers": ["file", "console"], "level": "WARNING", "propagate": False},
        "daphne": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "axes": {"handlers": ["security_file", "console"], "level": "WARNING", "propagate": False},
    },
}
```

---

## Step 3: Sentry Trace Correlation Filter

Create `core/logging_filters.py` -- add the `SentryTraceFilter` class alongside the existing `PIIMaskingFilter`:

```python
import logging

class SentryTraceFilter(logging.Filter):
    """
    Adds Sentry trace_id and span_id to log records for correlation.
    This allows you to link a log entry directly to a Sentry trace.
    """

    def filter(self, record):
        try:
            import sentry_sdk

            scope = sentry_sdk.get_current_scope()
            propagation_context = scope.get_isolation_scope()._propagation_context
            if propagation_context:
                record.trace_id = propagation_context.trace_id
                record.span_id = propagation_context.span_id
            else:
                record.trace_id = None
                record.span_id = None
        except Exception:
            record.trace_id = None
            record.span_id = None
        return True
```

### Output Example

With this filter, JSON log entries will include Sentry trace context:

```json
{
  "timestamp": "2026-04-06T10:15:23.456+03:00",
  "logger": "notifications",
  "level": "INFO",
  "message": "Notification sent to 45 recipients",
  "service": "schoolos",
  "environment": "production",
  "trace_id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
  "span_id": "f1e2d3c4b5a6f1e2"
}
```

To find all logs for a specific Sentry trace, search Railway logs for the `trace_id` value.

---

## Step 4: Log Levels Guide

### What to Log at Each Level

#### CRITICAL

System is unusable. Requires immediate human intervention.

```python
logger.critical("Database connection pool exhausted — all connections in use", extra={
    "pool_size": pool.size,
    "active_connections": pool.active,
})
```

Examples:
- Database connection pool exhausted
- Encryption key missing or corrupted
- Data integrity violation detected

#### ERROR

Operation failed but system continues. Needs investigation.

```python
logger.error("Failed to generate report card", extra={
    "student_pk": student.pk,  # PK only, never name
    "error_type": type(e).__name__,
}, exc_info=True)
```

Examples:
- Unhandled exception in a view (also captured by Sentry)
- Celery task failure after all retries
- External API call failure (SMS, email service)
- PDF generation failure

#### WARNING

Unexpected situation that may become a problem.

```python
logger.warning("Redis connection failed — falling back to local cache", extra={
    "redis_url_host": urlparse(REDIS_URL).hostname,  # host only, no credentials
    "fallback": "locmem",
})
```

Examples:
- Redis unavailable, using fallback cache
- Slow database query (> 1 second)
- Rate limit approaching threshold
- Failed login attempt (via django-axes)
- CORS origin mismatch in production
- S3 credentials missing, falling back to local storage

#### INFO

Normal operational events worth recording.

```python
logger.info("Notification batch sent", extra={
    "notification_type": "grade_published",
    "recipient_count": 45,
    "delivery_method": "websocket",
    "duration_ms": 120,
})
```

Examples:
- Notification sent (count, type, channel)
- Celery task started/completed (task name, duration)
- User login/logout (user PK only)
- Report generated (type, duration)
- Deploy completed (version, environment)
- Scheduled job executed (job name, result)

#### DEBUG

Detailed diagnostic information. **Never enable in production.**

```python
logger.debug("Cache lookup", extra={
    "cache_key": "student_list_page_1",
    "hit": True,
    "ttl_remaining": 245,
})
```

Examples:
- Cache hit/miss details
- SQL query text (development only)
- Template rendering details
- Middleware chain execution

---

## PDPPL: What NOT to Log

Qatar's Personal Data Privacy Protection Law (PDPPL) requires strict control over personal data. The `PIIMaskingFilter` provides automatic masking, but developers should avoid logging PII in the first place.

### Never Log These Fields

| Field | Why | Alternative |
|-------|-----|-------------|
| `national_id` / QID | Protected personal identifier | Use `student.pk` |
| `password` / `password_hash` | Credential data | Never log, even masked |
| `email` | Personal contact info | Use `user.pk` |
| `phone` / `mobile` | Personal contact info | Use `user.pk` |
| `date_of_birth` | Personal data | Use age range if needed |
| `address` | Personal data | Use city/district only |
| `parent_name` | Family data | Use `parent.pk` |
| `medical_conditions` | Health data (PDPPL Art. 13 sensitive) | Never log |
| `grades` with student identity | Educational records | Aggregate only |
| IP addresses | Network identity | Masked by PIIMaskingFilter |
| Session tokens / cookies | Authentication data | Never log |
| FERNET_KEY / SECRET_KEY | Cryptographic secrets | Never log |
| Database connection strings | Credentials | Log hostname only |

### Safe Logging Patterns

```python
# BAD -- logs PII
logger.info(f"Student {student.name} (QID: {student.national_id}) enrolled in {course.name}")

# GOOD -- uses PKs only
logger.info("Student enrolled in course", extra={
    "student_pk": student.pk,
    "course_pk": course.pk,
    "action": "enrollment",
})

# BAD -- logs credentials
logger.error(f"Redis connection failed: {REDIS_URL}")

# GOOD -- logs only the host
from urllib.parse import urlparse
logger.error("Redis connection failed", extra={
    "redis_host": urlparse(REDIS_URL).hostname,
    "redis_port": urlparse(REDIS_URL).port,
})
```

### PIIMaskingFilter Behavior

The existing `core.logging_filters.PIIMaskingFilter` automatically masks patterns in log messages:

| Pattern | Input | Output |
|---------|-------|--------|
| QID (11 digits) | `28760000001` | `287*****01` |
| Phone (+974...) | `+97466123456` | `****3456` |
| Email | `student@example.com` | `st***@example.com` |
| IP address | `192.168.1.100` | `192.***.***100` |

This is a safety net. The primary defense is to not log PII at all.

---

## Step 5: Structured Logging in Application Code

### Using Extra Fields

Always use the `extra` dict for structured data instead of f-strings:

```python
import logging

logger = logging.getLogger("notifications")

# Structured log entry
logger.info("Push notification sent", extra={
    "notification_type": "grade_published",
    "recipient_count": 45,
    "channel": "websocket",
    "duration_ms": 120,
    "success": True,
})
```

JSON output:

```json
{
  "timestamp": "2026-04-06T10:15:23.456+03:00",
  "logger": "notifications",
  "level": "INFO",
  "message": "Push notification sent",
  "notification_type": "grade_published",
  "recipient_count": 45,
  "channel": "websocket",
  "duration_ms": 120,
  "success": true,
  "service": "schoolos",
  "environment": "production",
  "trace_id": "a1b2c3d4..."
}
```

### Request Context Middleware

Add request metadata to all log entries within a request lifecycle:

```python
# core/middleware/logging_context.py
import logging
import time
import uuid

class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger("django.request")

    def __call__(self, request):
        request_id = str(uuid.uuid4())[:8]
        request.request_id = request_id
        start_time = time.monotonic()

        response = self.get_response(request)

        duration_ms = (time.monotonic() - start_time) * 1000

        if response.status_code >= 400:
            self.logger.warning("Request completed with error", extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 1),
                "user_pk": getattr(request.user, "pk", None),
            })

        return response
```

### Celery Task Logging

```python
# In any Celery task
import logging

logger = logging.getLogger("celery")

@app.task(bind=True)
def generate_report_pdf(self, report_pk):
    logger.info("Report generation started", extra={
        "task_id": self.request.id,
        "report_pk": report_pk,
        "task_name": "generate_report_pdf",
    })

    try:
        # ... generation logic ...
        logger.info("Report generation completed", extra={
            "task_id": self.request.id,
            "report_pk": report_pk,
            "duration_ms": duration,
            "file_size_kb": file_size // 1024,
        })
    except Exception as e:
        logger.error("Report generation failed", extra={
            "task_id": self.request.id,
            "report_pk": report_pk,
            "error_type": type(e).__name__,
        }, exc_info=True)
        raise
```

---

## Step 6: Railway Log Explorer Queries

Railway's log explorer supports text search across all stdout/stderr output. With JSON logging, you can search for specific fields.

### Common Queries

| What You Want | Search Query |
|---------------|-------------|
| All errors | `"level": "ERROR"` |
| All critical events | `"level": "CRITICAL"` |
| Specific trace | `a1b2c3d4` (the trace_id value) |
| Notification failures | `"logger": "notifications"` AND `"level": "ERROR"` |
| Celery task failures | `"logger": "celery"` AND `"level": "ERROR"` |
| Slow requests (> 1s) | `"duration_ms":` and look for values > 1000 |
| Security events | `SECURITY` (from security formatter) |
| Failed logins | `"logger": "axes"` |
| Specific request | The `request_id` value (e.g., `a1b2c3d4`) |
| Health check failures | `"path": "/health/"` AND `503` |

### Tips for Railway Logs

1. **Time range**: Use the time picker to narrow down to the incident window
2. **Service filter**: Select only the web service (exclude workers, cron)
3. **Export**: Railway allows exporting logs as text -- useful for postmortems
4. **Tail mode**: Use `railway logs --tail` for live debugging
5. **JSON parsing**: Railway does not natively parse JSON fields -- search by raw text

### Advanced: Forwarding Logs to Grafana Loki

For advanced log aggregation with Grafana Cloud:

1. Use the **Grafana Alloy** agent (free) as a sidecar or separate Railway service
2. Configure it to scrape Railway logs via the Railway API
3. Forward to Grafana Cloud Loki endpoint
4. Query with LogQL in Grafana:

```logql
{service="schoolos"} | json | level="ERROR"
{service="schoolos"} | json | logger="celery" | duration_ms > 5000
{service="schoolos"} | json | trace_id="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
```

---

## Migration Checklist

- [ ] Install `python-json-logger` and add to requirements
- [ ] Add `SentryTraceFilter` to `core/logging_filters.py`
- [ ] Update `LOGGING` config in `production.py` (add `json` formatter, update `console` handler)
- [ ] Test JSON output locally: `DJANGO_SETTINGS_MODULE=shschool.settings.production python -c "import logging; logging.warning('test')"`
- [ ] Deploy and verify JSON appears in Railway logs
- [ ] Update application code to use `extra` dict pattern
- [ ] Add `RequestLoggingMiddleware` if request-level logging is needed
- [ ] Verify PIIMaskingFilter still works with JSON output
- [ ] Test Sentry trace_id appears in log entries
