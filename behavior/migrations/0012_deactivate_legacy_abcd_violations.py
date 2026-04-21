"""
Data migration: تعطيل المخالفات القديمة (ABCD) نهائياً

السبب: طلب المدير أن تقتصر شاشة تسجيل السلوك على الـ 40 مخالفة
الرسمية من لائحة الشحانية (SOS-20260420-1E01) حرفياً — بدون بقايا قديمة.

الـ view في behavior/views.py يفلتر بـ is_active=True فقط. إذا بقيت
الـ ABCD بـ is_active=True تظهر للمستخدم. نعطّلها (soft) بدل الحذف
للحفاظ على سلامة FK لأي incident قديم.
"""

from django.db import migrations


def deactivate_legacy_abcd(apps, schema_editor):
    """تعطيل كل مخالفة لا تتبع نمط n-nn (أي ABCD أو غيرها)."""
    ViolationCategory = apps.get_model("behavior", "ViolationCategory")
    ViolationCategory.objects.exclude(code__regex=r"^\d+-\d+$").update(is_active=False)


def reverse_noop(apps, schema_editor):
    """لا نُعيد تفعيل المخالفات القديمة."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("behavior", "0011_normalize_violation_points_and_tags"),
    ]

    operations = [
        migrations.RunPython(deactivate_legacy_abcd, reverse_noop),
    ]
