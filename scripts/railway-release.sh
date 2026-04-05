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
echo "🎯 Starting gunicorn on 0.0.0.0:${PORT:-8080}"
echo "   workers=3, timeout=120, log-level=info"
echo ""
exec gunicorn shschool.wsgi:application \
  --bind "0.0.0.0:${PORT:-8080}" \
  --workers 3 \
  --worker-class sync \
  --timeout 120 \
  --access-logfile - \
  --error-logfile - \
  --log-level info \
  --capture-output
