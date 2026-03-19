"""
quality/migrations/0006_add_committee_constraint.py
الجزء الثاني: إضافة الـ UniqueConstraint في migration منفصلة
(يجب أن تكون بعد 0005 حتى لا يتعارض مع ترحيل البيانات)
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("quality", "0005_merge_committees_add_fields"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="qualitycommitteemember",
            constraint=models.UniqueConstraint(
                fields=["school", "academic_year", "user", "committee_type"],
                name="unique_member_per_committee_year",
            ),
        ),
        migrations.AddIndex(
            model_name="operationalprocedure",
            index=models.Index(fields=["deadline"], name="quality_ope_deadlin_idx"),
        ),
    ]
