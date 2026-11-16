"""W-20261116-003: ورقة الخروج بلا اعتماد — هجرةُ توسيعٍ فقط (حقولٌ بقيمٍ افتراضيّة، بلا حذف عمود)."""

from django.db import migrations, models

import core.fields


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0098_classexit_destination_ten"),
    ]

    operations = [
        migrations.AddField(
            model_name="exitpermit",
            name="guardian_method",
            field=models.CharField(
                blank=True,
                choices=[("present", "حضر ببطاقته"), ("phone", "اتّصال هاتفيّ")],
                db_default="",
                default="",
                max_length=8,
                verbose_name="طريقة موافقة وليّ الأمر",
            ),
        ),
        migrations.AddField(
            model_name="exitpermit",
            name="call_phone",
            field=core.fields.EncryptedTextField(
                blank=True, db_default="", default="", verbose_name="رقم الاتّصال"
            ),
        ),
        migrations.AddField(
            model_name="exitpermit",
            name="call_phone_registered",
            field=models.BooleanField(
                db_default=True, default=True, verbose_name="الرقمُ مسجَّلٌ لوليّ الأمر"
            ),
        ),
        migrations.AddField(
            model_name="exitpermit",
            name="caller_name",
            field=models.CharField(
                blank=True, db_default="", default="", max_length=150, verbose_name="اسم المتصل"
            ),
        ),
        migrations.AddField(
            model_name="exitpermit",
            name="caller_relation",
            field=models.CharField(
                blank=True, db_default="", default="", max_length=40, verbose_name="صلة المتصل"
            ),
        ),
        migrations.AlterField(
            model_name="exitpermit",
            name="status",
            field=models.CharField(
                choices=[("issued", "صادرة"), ("requested", "مطلوب"), ("approved", "معتمَد")],
                default="issued",
                max_length=10,
                verbose_name="الحالة",
            ),
        ),
    ]
