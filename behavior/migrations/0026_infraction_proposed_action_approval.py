"""W-20261108-027: اقتراحُ الإجراء من السلّم وتجهيزُه واعتمادُه — توسيعٌ فقط (حقولٌ فارغةٌ افتراضياً)."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("behavior", "0025_deactivate_points_columns")]

    operations = [
        migrations.AddField(
            model_name="behaviorinfraction",
            name="proposed_action",
            field=models.TextField(blank=True, default="", verbose_name="الإجراء المقترح من السلّم"),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="proposed_basis",
            field=models.CharField(
                blank=True,
                default="",
                max_length=160,
                verbose_name="سندُ الاقتراح (المادة والصفحة والتكرار)",
            ),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="specialist_line",
            field=models.CharField(
                blank=True,
                default="",
                max_length=300,
                verbose_name="سطرُ الإحالة للأخصائيّين من السلّم",
            ),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="prepared_action",
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
                related_name="prepared_infractions",
                to=settings.AUTH_USER_MODEL,
                verbose_name="جهّزها",
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
                choices=[
                    ("", "بلا اقتراح"),
                    ("pending", "بانتظار الاعتماد"),
                    ("approved", "معتمَد"),
                ],
                db_index=True,
                default="",
                max_length=10,
                verbose_name="حالة الاعتماد",
            ),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="follow_up",
            field=models.CharField(
                blank=True,
                choices=[("done", "تمّ"), ("not_done", "لم يتمّ"), ("partial", "جزئيًّا")],
                default="",
                max_length=10,
                verbose_name="المتابعة",
            ),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="approved_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="approved_infractions",
                to=settings.AUTH_USER_MODEL,
                verbose_name="اعتمدها",
            ),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="وقتُ الاعتماد"),
        ),
    ]
