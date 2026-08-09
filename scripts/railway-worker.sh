#!/bin/sh
set -eu

fail() {
    echo "::error:: $1" >&2
    exit 1
}

export DJANGO_SETTINGS_MODULE=shschool.settings.production

[ -n "${REDIS_URL:-}" ] || fail "REDIS_URL is required for the Celery worker."
[ -n "${APP_DB_PASSWORD:-}" ] || fail "APP_DB_PASSWORD is required for the Celery worker."
[ -n "${DB_HOST:-}" ] || fail "DB_HOST is required for the Celery worker."
[ -n "${DB_NAME:-}" ] || fail "DB_NAME is required for the Celery worker."
[ -n "${DB_PORT:-}" ] || fail "DB_PORT is required for the Celery worker."

# Never allow the worker runtime to fall back to Railway's owner/superuser DATABASE_URL.
unset DATABASE_URL
export DB_USER=shschool_app
export DB_PASSWORD="$APP_DB_PASSWORD"

echo "Verifying Celery worker database runtime role..."
python manage.py verify_runtime_db_role

echo "Starting Celery worker as shschool_app..."
exec celery -A shschool worker \
    --loglevel="${CELERY_LOG_LEVEL:-info}" \
    --concurrency="${CELERY_WORKER_CONCURRENCY:-2}" \
    --max-tasks-per-child="${CELERY_WORKER_MAX_TASKS_PER_CHILD:-100}"
