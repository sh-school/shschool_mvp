#!/usr/bin/env bash
# ══════════════════════════════════════════════
#  SchoolOS — إعداد بيئة التطوير المحلية
# ══════════════════════════════════════════════
set -e

echo "🚀 SchoolOS — بدء الإعداد..."

# Python venv
python3 -m venv .venv
source .venv/bin/activate

# Dependencies
pip install -r requirements.txt -q
echo "✅ المكتبات مثبتة"

# .env
if [ ! -f .env ]; then
  cp .env.example .env
  echo "✅ تم إنشاء .env — عدّل القيم قبل الإنتاج"
fi

# Database
createdb shschool_db 2>/dev/null || echo "⚠️  القاعدة موجودة مسبقاً"
echo "✅ قاعدة البيانات جاهزة"

# Migrations + seed
python manage.py migrate
echo "✅ Migrations مطبّقة"

python manage.py full_seed
echo "✅ البيانات محقونة (126 موظف، 742 طالب)"

# Static files
python manage.py collectstatic --noinput -q
echo "✅ الملفات الثابتة جاهزة"

# logs dir
mkdir -p logs

echo ""
echo "══════════════════════════════════"
echo "  SchoolOS جاهز للتشغيل! 🎉"
echo "══════════════════════════════════"
echo ""
echo "  شغّل: python manage.py runserver"
echo "  افتح: http://localhost:8000"
echo ""
echo "  🔑 بيانات الدخول:"
echo "  مدير:  28763400678 / school@2026"
echo "  طالب:  الرقم الشخصي / student@2026"
echo "  ولي أمر: الرقم الشخصي / parent@2026"
