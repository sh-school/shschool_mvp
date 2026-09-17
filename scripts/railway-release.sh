#!/bin/bash
# Railway Start Command — يُنفَّذ لكلّ نسخةٍ (replica) عند إقلاعها.
#
# الهجراتُ والبذرُ وتجميعُ الثابتِ وتوفيرُ دور RLS كانت هنا أيضاً، مكرَّرةً مع
# scripts/railway-predeploy.sh (preDeployCommand) كشبكة أمانٍ مؤقّتة حتى يُؤكَّد
# عملُ preDeploy على نشرٍ حقيقيّ (P4-1). تأكَّد ذلك 2026-09-17: سجلّ Railway
# (تبويب «Pre-Deploy» في لوحة النشر — لا تُظهره أداة السطر `railway logs`
# الافتراضيّة) يطبع «✅ Pre-Deploy Phase Complete» ثمّ «Stopping Container» /
# «Starting Container» قبل أن يبدأ هذا الملفّ. فحُذف التكرارُ من هنا — تقليصٌ
# بعد التوسيع.
set -e

echo "🎯 SchoolOS Start Phase — RLS guard + daphne"
echo "=============================================="

# ── حارسُ fail-closed: عزل المدارس (RLS) إلزاميّ في الإنتاج ──
# preDeploy وفّر الدورَ بالفعل؛ هذا الفحصُ دفاعٌ ثانٍ إن اختلف الإعدادُ بين
# مرحلتَي preDeploy وstart (لا يُفترض أن يختلف — كلتاهما تقرآن متغيّرات الخدمة نفسَها).
# بلا APP_DB_PASSWORD يعمل daphne بدور postgres (superuser) فيُتجاوَز RLS بصمت.
case "${DJANGO_SETTINGS_MODULE:-}" in
  *production*) _IS_PROD=1 ;;
  *) _IS_PROD=0 ;;
esac
if [ -z "$APP_DB_PASSWORD" ] && [ "$_IS_PROD" = "1" ]; then
  echo "::error:: APP_DB_PASSWORD غير مضبوط في الإنتاج — RLS لن يُفرَض. الإقلاع مرفوض (fail-closed). اضبط APP_DB_PASSWORD لتفعيل دور shschool_app."
  exit 1
fi

if [ -n "$APP_DB_PASSWORD" ]; then
  echo "🔐 RLS مفعّل: تشغيل daphne بدور shschool_app (غير-superuser) — الدورُ مُوفَّرٌ في preDeploy"
  exec env -u DATABASE_URL DB_USER=shschool_app DB_PASSWORD="$APP_DB_PASSWORD" \
    daphne -b 0.0.0.0 -p "${PORT:-8080}" --access-log - shschool.asgi:application
else
  echo "🎯 Starting daphne (ASGI) on 0.0.0.0:${PORT:-8080} (postgres — RLS متجاوَز؛ اضبط APP_DB_PASSWORD لتفعيله)"
  exec daphne -b 0.0.0.0 -p "${PORT:-8080}" --access-log - shschool.asgi:application
fi
