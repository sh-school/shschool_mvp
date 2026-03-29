# Generated manually 2026-03-28 — إرجاع درجة النجاح من 60 إلى 50

from decimal import Decimal

from django.db import migrations, models


def update_existing_pass_grades(apps, schema_editor):
    """تحديث السجلات الموجودة التي تستخدم 60 إلى 50."""
    AnnualSubjectResult = apps.get_model("assessments", "AnnualSubjectResult")
    AnnualSubjectResult.objects.filter(pass_grade=Decimal("60")).update(
        pass_grade=Decimal("50")
    )


def revert_pass_grades(apps, schema_editor):
    """إرجاع السجلات إلى 60."""
    AnnualSubjectResult = apps.get_model("assessments", "AnnualSubjectResult")
    AnnualSubjectResult.objects.filter(pass_grade=Decimal("50")).update(
        pass_grade=Decimal("60")
    )


class Migration(migrations.Migration):

    dependencies = [
        ("assessments", "0007_restructure_packages_and_aw_score"),
    ]

    operations = [
        migrations.AlterField(
            model_name="annualsubjectresult",
            name="pass_grade",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("50"),
                max_digits=5,
                verbose_name="درجة النجاح",
            ),
        ),
        migrations.RunPython(update_existing_pass_grades, revert_pass_grades),
    ]
