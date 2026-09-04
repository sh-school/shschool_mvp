# جرسُ كلّ نطاق: `TimeSlotConfig` يحمل النطاقَ، والفارغُ جرسُ المدرسة الافتراضيّ.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0049_timeband_classgroup_time_band"),
        ("operations", "0030_schedulingresource_same_level_only"),
    ]

    operations = [
        migrations.AddField(
            model_name="timeslotconfig",
            name="band",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="time_slots",
                to="core.timeband",
                verbose_name="نطاق التوقيت",
            ),
        ),
        migrations.AlterModelOptions(
            name="timeslotconfig",
            options={
                "ordering": ["band__order", "day_type", "period_number"],
                "verbose_name": "إعداد حصة زمنية",
                "verbose_name_plural": "إعدادات الحصص الزمنية",
            },
        ),
        migrations.RemoveConstraint(
            model_name="timeslotconfig",
            name="unique_timeslot_config",
        ),
        migrations.AddConstraint(
            model_name="timeslotconfig",
            constraint=models.UniqueConstraint(
                fields=("school", "band", "period_number", "day_type"),
                name="unique_timeslot_config",
            ),
        ),
    ]
