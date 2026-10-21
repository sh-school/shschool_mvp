# [W-20261020-029] ترميز زيارة العيادة — توسيعٌ فقط: أعمدةٌ جديدةٌ بقيمٍ افتراضيةٍ على مستوى القاعدة.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clinic", "0011_blood_type_legacy_release1"),
    ]

    operations = [
        migrations.AddField(
            model_name="clinicvisit",
            name="service_code",
            field=models.CharField(
                blank=True, db_default="", default="", max_length=40, verbose_name="الخدمة"
            ),
        ),
        migrations.AddField(
            model_name="clinicvisit",
            name="service_group",
            field=models.CharField(
                blank=True, db_default="", default="", max_length=20, verbose_name="مجموعة الخدمة"
            ),
        ),
        migrations.AddField(
            model_name="clinicvisit",
            name="complaint_code",
            field=models.CharField(
                blank=True, db_default="", default="", max_length=40, verbose_name="الشكوى"
            ),
        ),
        migrations.AddField(
            model_name="clinicvisit",
            name="outcome",
            field=models.CharField(
                blank=True, db_default="", default="", max_length=20, verbose_name="حالة الخروج"
            ),
        ),
        migrations.AddField(
            model_name="clinicvisit",
            name="closed_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="وقت إغلاق الزيارة"),
        ),
        migrations.AddField(
            model_name="clinicvisit",
            name="period_number",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="يُشتقّ من الجدول قراءةً فقط عند التسجيل؛ لا يُدخله الممرّض.",
                null=True,
                verbose_name="رقم الحصة (مشتقّ)",
            ),
        ),
    ]
