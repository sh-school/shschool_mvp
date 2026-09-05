#!/bin/bash
# Railway Release Phase — يُنفّذ قبل بدء الخادم
# يجري migrations + collectstatic + createsuperuser (أول مرة فقط)

set -e

echo "🚀 SchoolOS Railway Release Phase Starting..."
echo "=============================================="

# 1. Migrations
echo ""
echo "📦 Running database migrations..."
python manage.py migrate --noinput

# 1b. Seed classroom-observation criteria (idempotent — يزرع كل المدارس)
echo ""
echo "📋 Seeding classroom-observation criteria..."
python manage.py seed_observation_criteria || echo "  seed_observation_criteria skipped"

# 1b2. Seed any role added to the vocabulary (idempotent — get_or_create per school)
echo ""
echo "🧩 Seeding roles..."
python manage.py seed_new_roles || echo "  seed_new_roles skipped"

# 1c. Retire schedule slots & subject assignments left active from past years
#     العام يتبدّل بتاريخه من تقويم الوزارة، فجدول العام الماضي وإسناداته
#     تبقى نشطةً ما لم تُطفأ — ونسختان نشطتان تخلطان كل استعلام لا يُقيَّد
#     بالعام. (idempotent)
echo ""
echo "🗓  Retiring past-year schedule records..."
python manage.py retire_past_year_records --apply || echo "  retire_past_year_records skipped"

# 2. Collect static files
echo ""
echo "📁 Collecting static files..."
python manage.py collectstatic --noinput --clear

# 3. Create superuser if not exists (optional, from env vars)
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_EMAIL" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  echo ""
  echo "👤 Creating superuser (if not exists)..."
  python manage.py createsuperuser --noinput --username "$DJANGO_SUPERUSER_USERNAME" --email "$DJANGO_SUPERUSER_EMAIL" 2>/dev/null || echo "  Superuser already exists — skipping"
fi

# 4. Compile translations (if any)
if [ -d "locale" ]; then
  echo ""
  echo "🌍 Compiling translations..."
  python manage.py compilemessages 2>/dev/null || echo "  No translations to compile"
fi

# 5. Health check
echo ""
echo "🏥 Checking deployment health..."
python manage.py check --deploy 2>&1 | head -20 || echo "  Check passed with warnings"

echo ""

# 6. Reset axes lockouts if requested (one-time)
if [ "$RESET_AXES" = "1" ]; then
  echo "🔓 Resetting django-axes lockouts..."
  python manage.py axes_reset || echo "  axes_reset failed — skipping"
  echo "🔓 Clearing user lock fields..."
  python manage.py shell -c "from core.models.user import CustomUser; CustomUser.objects.update(failed_login_attempts=0, locked_until=None)" || echo "  user unlock failed"
fi

echo ""
echo "=============================================="
echo "✅ Release Phase Complete — Starting server..."
echo "=============================================="
echo ""
# ── تشغيل الخادم (ASGI/daphne) ─────────────────────────────────────
# migrate أعلاه عمل بدور المالك (DATABASE_URL=postgres) لتطبيق DDL.
# إن ضُبط APP_DB_PASSWORD: نوفّر دور التطبيق غير-superuser ونشغّل daphne به فيُفرَض RLS فعلياً.

# ── حارس fail-closed: عزل المدارس (RLS) إلزامي في الإنتاج ──
# بلا APP_DB_PASSWORD يعمل daphne بدور postgres (superuser) فيُتجاوَز RLS بصمت.
# في الإنتاج نرفض الإقلاع بدلاً من تشغيل المنصة بلا عزل بين المدارس (دفاع عميق).
case "${DJANGO_SETTINGS_MODULE:-}" in
  *production*) _IS_PROD=1 ;;
  *) _IS_PROD=0 ;;
esac
if [ -z "$APP_DB_PASSWORD" ] && [ "$_IS_PROD" = "1" ]; then
  echo "::error:: APP_DB_PASSWORD غير مضبوط في الإنتاج — RLS لن يُفرَض. الإقلاع مرفوض (fail-closed). اضبط APP_DB_PASSWORD لتفعيل دور shschool_app."
  exit 1
fi

if [ -n "$APP_DB_PASSWORD" ]; then
  echo "🔐 RLS مفعّل: توفير دور shschool_app (غير-superuser) ثم تشغيل daphne به"
  python manage.py provision_rls_role || { echo "::error:: فشل توفير دور RLS"; exit 1; }
  echo "🎯 Starting daphne (ASGI) as shschool_app on 0.0.0.0:${PORT:-8080} — RLS مُفرَض"
  exec env -u DATABASE_URL DB_USER=shschool_app DB_PASSWORD="$APP_DB_PASSWORD" \
    daphne -b 0.0.0.0 -p "${PORT:-8080}" --access-log - shschool.asgi:application
else
  echo "🎯 Starting daphne (ASGI) on 0.0.0.0:${PORT:-8080} (postgres — RLS متجاوَز؛ اضبط APP_DB_PASSWORD لتفعيله)"
  exec daphne -b 0.0.0.0 -p "${PORT:-8080}" --access-log - shschool.asgi:application
fi
