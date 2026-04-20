"""
Data migration: تحديث قائمة المخالفات السلوكية وفق لائحة مدرسة الشحانية
SOS-20260420-1E01 — 40 مخالفة × 4 درجات

تعتمد هذه الـ migration على VIOLATIONS_2025 في behavior/constants.py
(Single Source of Truth — لا تكرار للقائمة هنا)
"""
from django.db import migrations

from behavior.constants import VIOLATIONS_2025


def update_violations(apps, schema_editor):
    """حذف المخالفات الرسمية القديمة وحقن الجديدة."""
    ViolationCategory = apps.get_model("behavior", "ViolationCategory")

    # حذف المخالفات ذات الترميز الرسمي (n-nn) — القديمة والجديدة معاً
    ViolationCategory.objects.filter(code__regex=r"^\d+-\d+$").delete()

    for degree, code, name_ar, points, tag_list in VIOLATIONS_2025:
        ViolationCategory.objects.get_or_create(
            code=code,
            defaults={
                "degree": degree,
                "name_ar": name_ar,
                "points": points,
                "tags": ",".join(tag_list),
                "is_active": True,
                "requires_security_referral": degree == 4,
                "requires_parent_summon": degree >= 3,
            },
        )


def reverse_violations(apps, schema_editor):
    """Reverse: delete Shahaniya violations (no restore of old)."""
    ViolationCategory = apps.get_model("behavior", "ViolationCategory")
    ViolationCategory.objects.filter(code__regex=r"^\d+-\d+$").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("behavior", "0009_req_sh_001_disciplinary_action"),
    ]

    operations = [
        migrations.RunPython(update_violations, reverse_violations),
    ]
