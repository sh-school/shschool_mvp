# [W-20261020-035] قياس زمن التسجيل — توسيعٌ فقط: عمودٌ يقبل NULL بلا قيمةٍ افتراضية.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clinic", "0018_clinicvisit_infectious_alert"),
    ]

    operations = [
        migrations.AddField(
            model_name="clinicvisit",
            name="draft_started_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="وقت بدء المسودة (للقياس)"
            ),
        ),
    ]
