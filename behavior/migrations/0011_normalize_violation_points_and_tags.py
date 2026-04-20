"""
Data migration: توحيد نقاط المخالفات حسب POINTS_BY_LEVEL وإفراغ الـ tags
SOS-20260420-1E01 (follow-up) — تطبيق طلب المدير حرفياً (نصوص فقط، بلا اجتهاد)

السبب:
- المدير ذكر النصوص الأربعين فقط ولم يذكر points/tags
- الـ migration 0010 حقنت قيماً اجتهادية للـ points والـ tags
- هذه الـ migration تعيد ضبطها على POINTS_BY_LEVEL القياسي + تُفرغ tags
"""
from django.db import migrations

from behavior.constants import POINTS_BY_LEVEL


def normalize_points_and_tags(apps, schema_editor):
    """تحديث المخالفات الرسمية (n-nn) لتأخذ نقاط الدرجة الموحّدة وتفرغ tags."""
    ViolationCategory = apps.get_model("behavior", "ViolationCategory")
    for row in ViolationCategory.objects.filter(code__regex=r"^\d+-\d+$"):
        row.points = POINTS_BY_LEVEL.get(row.degree, row.points)
        row.tags = ""
        row.save(update_fields=["points", "tags"])


def reverse_noop(apps, schema_editor):
    """Non-reversible — لا نعيد القيم الاجتهادية السابقة."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("behavior", "0010_update_violations_shahaniya"),
    ]

    operations = [
        migrations.RunPython(normalize_points_and_tags, reverse_noop),
    ]
