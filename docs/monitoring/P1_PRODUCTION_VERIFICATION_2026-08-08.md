# P1 Production Verification Receipt — 2026-08-08

```text
STATUS             = PASS / PRODUCTION-RUNTIME-VERIFIED
REPOSITORY         = sh-school/shschool_mvp
PRODUCTION_COMMIT  = 4043763f985192b8fcd491f46290e3b375e738dc
PLATFORM           = Railway
ENVIRONMENT        = production
MANUAL_REDEPLOY    = NO
VARIABLE_MUTATION  = NO
DATABASE_MUTATION  = NO
```

## Verified live

- Railway deployed the exact merged P1 commit from main.
- /health/ returned 200.
- /ready/ returned 200.
- /status/ remained protected with 302.
- /metrics remained protected with 403.
- Django cache backend is RedisCache.
- Redis cache write/read/delete round-trip passed.
- Sessions remain database-backed.
- CELERY_TASK_ALWAYS_EAGER=True.
- CELERY_TASK_EAGER_PROPAGATES=False.
- Redis Channel Layer send/receive round-trip passed.
- Anonymous Notifications WebSocket was rejected with 403.
- Anonymous Attendance WebSocket was rejected with 403.
- Authenticated Notifications WebSocket returned 101.
- Authorized Attendance WebSocket returned 101.
- Nonexistent Attendance session was rejected with 403.
- Sentry SDK runtime client is active with a transport.
- Django, Celery, Redis, and Logging Sentry integrations are active.
- Sentry send_default_pii=False.
- Sentry before_send and traces_sampler are configured.

## Explicit verification boundaries

- Cross-school live WebSocket denial: NOT TESTED; no safe production multi-school candidate existed.
- Same-school unrelated-teacher live denial: NOT TESTED; no safe production candidate existed.
- Sentry event ingestion end-to-end: NOT TESTED; no synthetic event was sent.
- Dedicated asynchronous Celery worker: NOT VERIFIED.
- CELERY_ASYNC_ENABLED remains disabled/not enabled.

## Final verdict

```text
P1_PRODUCTION_VERIFICATION = PASS
REDIS_CACHE               = PASS
REDIS_CHANNEL_LAYER       = PASS
EXTERNAL_WSS              = PASS
AUTHENTICATED_WSS         = PASS
DB_SESSIONS               = PASS
CELERY_EAGER_POLICY       = PASS
SENTRY_RUNTIME            = PASS
```

No secret, DSN, Redis URL, database URL, session key, user ID, school ID,
or attendance-session ID is recorded in this receipt.
