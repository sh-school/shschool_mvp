"""آخرُ يومٍ في الشعبة على قيد الطالب — توسيعٌ بحقلٍ فارغٍ بلا افتراضٍ إلزاميّ (W-20261010-017، D-323م)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0084_acting_assignment_audit_and_coordinator"),
    ]

    operations = [
        migrations.AddField(
            model_name="studentenrollment",
            name="left_at",
            field=models.DateField(
                blank=True,
                help_text="يُكتب عند النقل الداخلي: آخرُ يومٍ يُحسب فيه الطالبُ في هذه الشعبة؛ فارغٌ لمن لم يُنقل.",
                null=True,
                verbose_name="آخر يوم في الشعبة",
            ),
        ),
    ]
