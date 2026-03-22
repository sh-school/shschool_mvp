#!/usr/bin/env python
"""
seed_all.py — حقن كامل لجميع البيانات الحقيقية
يشغّل كل المراحل بالترتيب الصحيح:
  1. البيانات التجريبية (اختياري)
  2. الموظفون + الطلاب + أولياء الأمور (الحقيقي)
  3. الخطة التشغيلية + لجنة الجودة

تشغيل:
    python manage.py seed_all
أو:
    python manage.py shell < scripts/seed_all.py
"""

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shschool.settings.development")

# إضافة جذر المشروع لمسار الاستيراد
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import django

django.setup()

# ── التحقق من وجود ملفات البيانات ──────────────────────────
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

REQUIRED_FILES = [
    "2_Normalized_Staff_List.csv",
    "new_students_full.csv",
    "1_Clean_Operational_Plan.csv",
    "4_Quality_Structure_v2.csv",
    "3_Unique_Executors_Inventory.csv",
]

print("=" * 60)
print("🏫 SchoolOS — حقن البيانات الكامل")
print("   مدرسة الشحانية الإعدادية الثانوية للبنين")
print("=" * 60)
print(f"\n📁 مجلد البيانات: {DATA_DIR}\n")

missing = []
for f in REQUIRED_FILES:
    path = DATA_DIR / f
    if path.exists():
        size = path.stat().st_size // 1024
        print(f"  ✅ {f} ({size} KB)")
    else:
        print(f"  ❌ {f} — غير موجود!")
        missing.append(f)

if missing:
    print("\n⛔ يرجى إضافة الملفات الناقصة في مجلد data/")
    sys.exit(1)

print("\n" + "-" * 60)
input("\n▶ اضغط Enter للبدء... (Ctrl+C للإلغاء)\n")

start = time.time()

# ── المرحلة 1: الموظفون + الطلاب + أولياء الأمور ──────────
print("\n" + "═" * 60)
print("📥 المرحلة 1: الموظفون والطلاب وأولياء الأمور")
print("═" * 60)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from real_seed import run as run_real_seed

run_real_seed()

# ── المرحلة 2: الخطة التشغيلية + لجنة الجودة ──────────────
print("\n" + "═" * 60)
print("📋 المرحلة 2: الخطة التشغيلية + لجنة المراجعة الذاتية")
print("═" * 60)

from seed_quality import run as run_quality

run_quality()

# ── ملخص نهائي ──────────────────────────────────────────────
elapsed = round(time.time() - start, 1)

from core.models import ClassGroup, CustomUser, School, StudentEnrollment
from quality.models import OperationalProcedure, QualityCommitteeMember

school = School.objects.get(code="SHH")

print("\n" + "═" * 60)
print("🎉 اكتمل الحقن الكامل!")
print(f"   الوقت المستغرق: {elapsed} ثانية")
print("═" * 60)
print(f"  👤 المستخدمون:           {CustomUser.objects.count()}")
print(f"  🏫 الفصول الدراسية:      {ClassGroup.objects.filter(school=school).count()}")
print(
    f"  📝 تسجيلات الطلاب:       {StudentEnrollment.objects.filter(class_group__school=school).count()}"
)
print(f"  📋 الإجراءات التشغيلية:  {OperationalProcedure.objects.filter(school=school).count()}")
print(
    f"  🏛️  لجنة الجودة:          {QualityCommitteeMember.objects.filter(school=school).count()} عضو"
)
print("═" * 60)
print("\n── بيانات الدخول ─────────────────────────────────────")
print("  المدير:      28763400678    /  school@2026")
print("  المعلمون:    <الرقم الوطني> /  school@2026")
print("  الطلاب:      <الرقم الوطني> /  student@2026")
print("  الأولياء:    <الرقم الوطني> /  parent@2026")
print("  Django Admin: /admin/")
print("═" * 60)


if __name__ == "__main__":
    pass  # تم التشغيل أعلاه مباشرةً
