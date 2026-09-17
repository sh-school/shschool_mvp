#!/bin/bash
# Railway Start Command — يُنفَّذ لكلّ نسخةٍ (replica) عند إقلاعها.
#
# حادثة 2026-09-17: نُقل تجميعُ الثابت من هنا إلى preDeploy وحدَه (#311)
# بذريعة أنّه «مكرَّرٌ» مع الهجرات والبذر — لكنّه ليس كذلك. الهجراتُ والبذرُ
# يكتبان في القاعدة المشتركة، فمرّةٌ واحدةٌ في preDeploy تكفي كلَّ نسخة.
# أمّا `collectstatic` فيكتب في القرص المحلّيّ للحاوية (`STATIC_ROOT`)، وحاويةُ
# preDeploy حاويةٌ عابرةٌ منفصلةٌ عن حاويات النسخ الفعليّة التي يشغّلها Railway
# بعده — فما كُتب هناك لا يصل هنا. فسقطت المنصّةُ كاملةً: كلُّ صفحةٍ 500، حتى
# صفحةَ الخطأ نفسَها لأنّ قالبها أيضاً يستدعي {% static %} لخطّ Tajawal، فرفع
# `ValueError: Missing staticfiles manifest entry` قبل أن يُرسَم أيُّ ردّ.
# فعاد `collectstatic` إلى هنا — لكلّ نسخةٍ، في حاويتها هي التي تخدم الحركة.
set -e

echo "🎯 SchoolOS Start Phase — static + RLS guard + daphne"
echo "=============================================="

echo "📁 Collecting static files (نسخةٌ محليّةٌ لهذه الحاوية)..."
python manage.py collectstatic --noinput --clear

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
