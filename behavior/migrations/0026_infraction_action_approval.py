"""W-20261112-003: اعتمادُ إجراء المخالفة — توسيعٌ فقط على نموذج المخالفة (لا حذفَ ولا تغييرَ أعمدة)."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("behavior", "0025_deactivate_points_columns"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="behaviorinfraction",
            name="prepared_kind",
            field=models.CharField(
                blank=True,
                choices=[("written_pledge", "تعهّد خطّي"), ("referral", "إحالة")],
                default="",
                max_length=20,
                verbose_name="ما جُهِّز",
            ),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="prepared_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="prepared_infractions",
                to=settings.AUTH_USER_MODEL,
                verbose_name="جهّزه",
            ),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="prepared_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="وقت التجهيز"),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="action_approved_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="approved_infraction_actions",
                to=settings.AUTH_USER_MODEL,
                verbose_name="اعتمد الإجراء",
            ),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="action_approved_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="وقت الاعتماد"),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="action_followup",
            field=models.CharField(
                blank=True,
                choices=[("done", "تمّ"), ("not_done", "لم يتمّ"), ("partial", "جزئيًّا")],
                default="",
                max_length=10,
                verbose_name="متابعة التنفيذ",
            ),
        ),
    ]
