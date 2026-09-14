"""مراجعةُ العذر عند النائب الإداريّ — «بانتظار النائب» بعد مهلة العودة (قرارُ 2026-09-14)."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0052_guardian_contact"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="absenceexcuse",
            name="rejection_reason",
            field=models.TextField(blank=True, verbose_name="سببُ الرفض"),
        ),
        migrations.AddField(
            model_name="absenceexcuse",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="absenceexcuse",
            name="reviewed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="absence_excuses_reviewed",
                to=settings.AUTH_USER_MODEL,
                verbose_name="قرّره النائب",
            ),
        ),
        migrations.AddField(
            model_name="absenceexcuse",
            name="status",
            field=models.CharField(
                choices=[
                    ("accepted", "مقبول"),
                    ("pending", "بانتظار النائب الإداريّ"),
                    ("rejected", "مرفوض"),
                ],
                db_index=True,
                default="accepted",
                max_length=10,
                verbose_name="الحالة",
            ),
        ),
    ]
