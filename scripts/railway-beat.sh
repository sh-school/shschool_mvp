#!/bin/sh
# Celery Beat — مُرسِلُ الجدول لا مُنفِّذُه: يقرأ `beat_schedule` من الشيفرة ويضع المهامَّ
# في الوسيط عند مواعيدها، والعاملُ ينفّذها. كان غائباً عن Railway منذ الإنشاء فكانت
# تنبيهاتُ الغياب ومهلُ الخروقات وإلغاءُ الصلاحيّات المؤقّتة ميتةً في الإنتاج (سواط 2026-09-14).
# نسخةٌ واحدةٌ فقط — نسختان تُرسلان كلَّ مهمّةٍ مرّتين.
set -eu

fail() {
    echo "::error:: $1" >&2
    exit 1
}

export DJANGO_SETTINGS_MODULE=shschool.settings.production

[ -n "${REDIS_URL:-}" ] || fail "REDIS_URL is required for Celery Beat."
[ "${CELERY_ASYNC_ENABLED:-false}" = "true" ] || fail "CELERY_ASYNC_ENABLED=true is required — Beat without a worker queue sends into the void."
[ -n "${APP_DB_PASSWORD:-}" ] || fail "APP_DB_PASSWORD is required (Django settings load the database)."
[ -n "${DB_HOST:-}" ] || fail "DB_HOST is required."
[ -n "${DB_NAME:-}" ] || fail "DB_NAME is required."
[ -n "${DB_PORT:-}" ] || fail "DB_PORT is required."

# كالعامل: لا سقوطَ إلى DATABASE_URL بدور المالك.
unset DATABASE_URL
export DB_USER=shschool_app
export DB_PASSWORD="$APP_DB_PASSWORD"

echo "Starting Celery Beat (schedule from shschool/celery.py, state file in /tmp)..."
exec celery -A shschool beat \
    --loglevel="${CELERY_LOG_LEVEL:-info}" \
    --schedule=/tmp/celerybeat-schedule
