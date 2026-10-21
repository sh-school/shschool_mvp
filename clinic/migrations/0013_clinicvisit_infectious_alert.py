# [W-20261020-042] الحالة المعدية وقرار الإبلاغ وتنبيه المعلّم — توسيعٌ فقط: أعمدةٌ جديدةٌ بقيمٍ افتراضيةٍ أو قابلةٍ للفراغ.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clinic", "0012_clinicvisit_coding"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="clinicvisit",
            name="infectious_status",
            field=models.CharField(
                blank=True,
                db_default="",
                default="",
                max_length=20,
                verbose_name="الحالة المعدية",
            ),
        ),
        migrations.AddField(
            model_name="clinicvisit",
            name="external_report_decision",
            field=models.CharField(
                blank=True,
                db_default="",
                default="",
                max_length=20,
                verbose_name="قرار الإبلاغ الخارجي",
            ),
        ),
        migrations.AddField(
            model_name="clinicvisit",
            name="external_report_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="clinic_report_decisions",
                to=settings.AUTH_USER_MODEL,
                verbose_name="قرّر الإبلاغ",
            ),
        ),
        migrations.AddField(
            model_name="clinicvisit",
            name="external_report_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="وقت قرار الإبلاغ"
            ),
        ),
        migrations.AddField(
            model_name="clinicvisit",
            name="teacher_alerted_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="وقت تنبيه معلّم الحصة"
            ),
        ),
    ]
