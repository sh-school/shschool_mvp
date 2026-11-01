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

# ملفّاتُ الثابت في القرص المحلّيّ لهذه الحاوية (`STATIC_ROOT`) لا في قرصٍ مشترك: حاويةُ العامل تبدأ بمجلّدٍ فارغٍ بلا
# `staticfiles.json`، فكلُّ قالبٍ فيه `{% static %}` يُصيَّر داخل العامل — كقالب طباعة الجدول (`print_schedule.html`)
# لتصدير PDF — يرفع `ValueError: Missing staticfiles manifest entry` فيفشل التصدير. وهذا السطرُ كما في
# `railway-release.sh` (الإعدادُ production نفسُه، ولا يحتاج القاعدة). ويحرسه `tests/test_worker_collects_static.py`:
# يفشل إن غاب أو جاء بعد `exec celery`.
echo "Collecting static files (نسخةٌ محليّةٌ لحاوية العامل)..."
python manage.py collectstatic --noinput --clear

# W-20261031-004: Beat مضمَّنٌ في العامل (-B) بدل خدمةٍ مستقلّةٍ تحجز ~186MB لإرسال الجدول وحدَه.
# العلمُ افتراضيُّه مُطفأ: تشغيلُه والخدمةُ المستقلّةُ قائمتان يُرسل كلَّ مهمّةٍ مجدولةٍ مرّتين.
# التسلسل: أوقف خدمة celery-beat ثمّ اضبط CELERY_WORKER_EMBED_BEAT=true على العامل (docs/railway_usage_2026-10-31.md).
# نسخةٌ واحدةٌ فقط من العامل مع هذا العلم، وإلّا تكرّر الإرسال.
BEAT_ARGS=""
if [ "${CELERY_WORKER_EMBED_BEAT:-false}" = "true" ]; then
    [ "${CELERY_ASYNC_ENABLED:-false}" = "true" ] || fail "CELERY_ASYNC_ENABLED=true is required to embed Beat in the worker."
    echo "Embedding Celery Beat in the worker (-B, state file in /tmp)..."
    BEAT_ARGS="--beat --schedule=/tmp/celerybeat-schedule"
fi

echo "Starting Celery worker as shschool_app..."
# shellcheck disable=SC2086 — BEAT_ARGS كلماتٌ مقصودةُ التقسيم أو فارغة
exec celery -A shschool worker \
    --loglevel="${CELERY_LOG_LEVEL:-info}" \
    --concurrency="${CELERY_WORKER_CONCURRENCY:-2}" \
    --max-tasks-per-child="${CELERY_WORKER_MAX_TASKS_PER_CHILD:-100}" \
    $BEAT_ARGS
