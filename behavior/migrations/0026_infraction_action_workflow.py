"""W-20261108-005: اقتراحُ الإجراء وتجهيزُه ومتابعتُه واعتمادُه على المخالفة — توسيعٌ فقط.

أعمدةٌ جديدةٌ بقيمٍ افتراضيّةٍ فارغةٍ ومفاتيحَ اختياريّة؛ لا يُحذف ولا يُعدَّل عمودٌ قائم.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _user_fk(label: str) -> models.ForeignKey:
    return models.ForeignKey(
        blank=True,
        null=True,
        on_delete=django.db.models.deletion.SET_NULL,
        related_name="+",
        to=settings.AUTH_USER_MODEL,
        verbose_name=label,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("behavior", "0025_deactivate_points_columns"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="behaviorinfraction",
            name="suggested_action",
            field=models.CharField(
                blank=True, default="", max_length=1000, verbose_name="الإجراء المقترح من السلّم"
            ),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="suggested_source",
            field=models.CharField(
                blank=True,
                default="",
                max_length=200,
                verbose_name="مصدر الاقتراح (المادة والصفحة)",
            ),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="suggested_step",
            field=models.PositiveSmallIntegerField(default=0, verbose_name="مرّة التكرار المقترحة"),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="specialist_listed",
            field=models.BooleanField(default=False, verbose_name="في قائمة الاختصاصيَّين"),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="prepared_kind",
            field=models.CharField(
                blank=True,
                choices=[("written_pledge", "تعهّد خطّي"), ("referral", "إحالة")],
                default="",
                max_length=20,
                verbose_name="ما جهّزه المشرف",
            ),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="prepared_by",
            field=_user_fk("جهّزه"),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="prepared_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="وقت التجهيز"),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="followup_status",
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
            name="followed_by",
            field=_user_fk("تابعه"),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="followed_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="وقت المتابعة"),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="approved_action",
            field=models.CharField(
                blank=True, default="", max_length=1000, verbose_name="الإجراء المعتمد"
            ),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="approved_by",
            field=_user_fk("اعتمده"),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="وقت الاعتماد"),
        ),
    ]
