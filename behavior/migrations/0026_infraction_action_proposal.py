"""W-20261108-007: اقتراحُ إجراء المخالفة من السلّم وتجهيزُه واعتمادُه — توسيعٌ فقط (حقولٌ جديدةٌ بقيمٍ افتراضيّة)."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("behavior", "0025_deactivate_points_columns"),
    ]

    operations = [
        migrations.AddField(
            model_name="behaviorinfraction",
            name="proposed_rep",
            field=models.PositiveSmallIntegerField(
                blank=True, null=True, verbose_name="تكرارُ السلّم المقترح"
            ),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="proposed_text",
            field=models.TextField(blank=True, default="", verbose_name="الإجراء المقترح"),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="proposed_source",
            field=models.CharField(
                blank=True,
                default="",
                max_length=200,
                verbose_name="سندُ الاقتراح (الملفّ والمادّة والسطر)",
            ),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="proposed_specialist",
            field=models.BooleanField(default=False, verbose_name="عتبةُ إحالةٍ للاختصاصيّين"),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="prepared_kind",
            field=models.CharField(
                blank=True,
                choices=[("written_pledge", "تعهّدٌ خطّيّ"), ("referral", "إحالة")],
                default="",
                max_length=20,
                verbose_name="ما جهّزه مشرفُ الجناح",
            ),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="prepared_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                verbose_name="جهّزه",
            ),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="prepared_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="وقتُ التجهيز"),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="approval_status",
            field=models.CharField(
                blank=True,
                choices=[("pending", "بانتظار الاعتماد"), ("approved", "مُعتمَد")],
                db_index=True,
                default="",
                max_length=10,
                verbose_name="حالةُ اعتماد الإجراء",
            ),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="follow_up",
            field=models.CharField(
                blank=True,
                choices=[("done", "تمّ"), ("not_done", "لم يتمّ"), ("partial", "جزئيّاً")],
                default="",
                max_length=10,
                verbose_name="متابعةُ التنفيذ",
            ),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="approved_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                verbose_name="اعتمده",
            ),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="وقتُ الاعتماد"),
        ),
    ]
