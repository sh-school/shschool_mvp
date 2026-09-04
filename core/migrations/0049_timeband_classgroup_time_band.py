# نطاقاتُ التوقيت: طابقان بجرسين (والخميسُ ثلاثة). رقمُ الحصّة لا يعني الوقتَ
# نفسَه في النطاقين، فتُنسب الشعبةُ إلى نطاقها ويُحكَم معلّمُ الطابقين بالساعة.
# التوزيعُ الزمنيّ للحصص 2025–2026 (أكتوبر) — مؤكَّدٌ ساريَ العام 2026–2027.

import core.models.school
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0048_rls_reconcile_branch_policies"),
    ]

    operations = [
        migrations.CreateModel(
            name="TimeBand",
            fields=[
                ("id", models.UUIDField(default=core.models.school._uuid, editable=False, primary_key=True, serialize=False)),
                ("code", models.SlugField(max_length=20, verbose_name="الرمز")),
                ("name", models.CharField(max_length=60, verbose_name="الاسم")),
                ("order", models.PositiveSmallIntegerField(default=0, verbose_name="الترتيب")),
                ("is_active", models.BooleanField(default=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="time_bands",
                        to="core.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "نطاق توقيت",
                "verbose_name_plural": "نطاقات التوقيت",
                "ordering": ["order", "code"],
            },
        ),
        migrations.AddConstraint(
            model_name="timeband",
            constraint=models.UniqueConstraint(fields=("school", "code"), name="unique_time_band_per_school"),
        ),
        migrations.AddField(
            model_name="classgroup",
            name="time_band",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="class_groups",
                to="core.timeband",
                verbose_name="نطاق التوقيت",
            ),
        ),
    ]
