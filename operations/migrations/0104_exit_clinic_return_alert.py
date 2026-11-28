"""مسارُ العيادة 2: مرحلةُ تنبيه العائد من العيادة على `ClassExit`.

عمودٌ واحدٌ بقيمةٍ افتراضيّة: إضافةٌ يحذفها التراجعُ بلا فقدِ بياناتٍ سابقة.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("operations", "0103_exit_clinic_moments_excused")]

    operations = [
        migrations.AddField(
            model_name="classexit",
            name="clinic_alert_stage",
            field=models.PositiveSmallIntegerField(
                default=0, verbose_name="مرحلةُ تنبيه العودة من العيادة"
            ),
        ),
    ]
