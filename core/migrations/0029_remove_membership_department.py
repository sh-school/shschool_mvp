"""
Migration 0029 — إزالة حقل department النصي من Membership
الجزء الأخير من Phase 3: توحيد القسم على FK فقط (department_obj)
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0028_add_performance_indexes"),
    ]

    operations = [
        # 1. أولاً: نزيل الـ index (يعتمد على العمود)
        migrations.RemoveIndex(
            model_name="membership",
            name="idx_active_dept",
        ),
        # 2. ثانياً: نزيل العمود نفسه
        migrations.RemoveField(
            model_name="membership",
            name="department",
        ),
    ]
