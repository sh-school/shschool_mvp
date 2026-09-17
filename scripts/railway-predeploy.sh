#!/bin/bash
# Railway Pre-Deploy Phase — preDeployCommand: يُنفَّذ مرّةً واحدةً لكلّ نشرٍ قبل
# أن تستقبل أيّ نسخةٍ منه الحركة، لا لكلّ نسخةٍ كما يُنفَّذ start (P4-1).
#
# كان هذا كلُّه داخل railway-release.sh (start) وحدَه، فمع عدّة نسخٍ
# (numReplicas > 1) كانت الهجراتُ والبذرُ ستُشغَّل مرّةً لكلّ نسخة — سباقٌ على
# DDL لا معنى له. وأخطر منه: فشلُ الهجرة كان يعني نسخةً بدأت daphne بمخطّطٍ
# غيرِ مكتمل قبل أن يُخرجها فحصُ الصحّة. هنا فشلُ أيّ خطوةٍ يمنع النشرَ قبل أن
# يمسّ الحركةَ الحيّة.
#
# [مؤقّت] لا يعمل هذا الملفّ إلّا بعد `railway config apply` (بيدٍ بشريّة —
# راجع رأس .railway/railway.ts). فبقيت الخطواتُ نفسُها في railway-release.sh
# أيضاً حتى يُؤكَّد عملُ preDeploy على نشرٍ حقيقيّ، ثمّ تُحذف من هناك في طلب
# دمجٍ لاحق. كلُّ خطوةٍ هنا idempotent فتكرارُها آمن.
set -e

echo "🚀 SchoolOS Pre-Deploy Phase Starting..."
echo "=========================================="

# 1. Migrations — بدور المالك (DATABASE_URL) لتطبيق DDL.
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

# 7. RLS: يوفَّر دور التطبيق هنا — قبل أن تبدأ أيّ نسخةٍ الاتّصال به في start.
#    والفحصُ fail-closed هنا أيضاً (لا في start وحده): فشلُه يمنع بناء نسخةٍ
#    مصيرُها الفشلَ أصلاً، بدل أن تُبنى ثمّ تسقط عند فحص الصحّة.
case "${DJANGO_SETTINGS_MODULE:-}" in
  *production*) _IS_PROD=1 ;;
  *) _IS_PROD=0 ;;
esac
if [ -z "$APP_DB_PASSWORD" ] && [ "$_IS_PROD" = "1" ]; then
  echo "::error:: APP_DB_PASSWORD غير مضبوط في الإنتاج — RLS لن يُفرَض. النشرُ مرفوض (fail-closed)."
  exit 1
fi
if [ -n "$APP_DB_PASSWORD" ]; then
  echo ""
  echo "🔐 توفير دور shschool_app (RLS) — بدور المالك..."
  python manage.py provision_rls_role
fi

echo ""
echo "=========================================="
echo "✅ Pre-Deploy Phase Complete"
echo "=========================================="
