import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    """توسيعٌ فقط (W-20261003-035): عمودٌ يقبل NULL لسقف السابعة الأسبوعيّ الخاصّ بمعلّم — لا يمسّ قراءةً ولا كتابةً قائمة."""

    dependencies = [
        ("operations", "0064_attendance_unobserved_correction"),
    ]

    operations = [
        migrations.AddField(
            model_name="teacherpreference",
            name="max_last_periods",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="قرارٌ إداريّ في حقّ هذا المعلّم — فارغٌ يعني السقفَ العامّ (اثنتان)",
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(5),
                ],
                verbose_name="أقصى سابعات أسبوعيّاً",
            ),
        ),
    ]
