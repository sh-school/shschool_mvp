"""[W-029] توسيع: حقلٌ مشفَّر لفصيلة الدم بجوار العمود الصريح القديم.

الخطوةُ الأولى من اثنتين (قاعدة «توسيعٌ ثمّ تقليص»): إضافةٌ فقط، والقديمُ
باقٍ. الملءُ في 0008، وحذفُ القديم طلبٌ لاحقٌ بعد استقرار الإصدار.
`default` مع `db_default` معاً كي لا تسقط كتابةُ النسخة القديمة أثناء النشر.
"""

import core.fields
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("clinic", "0006_arabic_field_labels"),
    ]

    operations = [
        migrations.AddField(
            model_name="healthrecord",
            name="blood_type_encrypted",
            field=core.fields.EncryptedTextField(
                blank=True,
                choices=[
                    ("A+", "A+"),
                    ("A-", "A-"),
                    ("B+", "B+"),
                    ("B-", "B-"),
                    ("AB+", "AB+"),
                    ("AB-", "AB-"),
                    ("O+", "O+"),
                    ("O-", "O-"),
                ],
                db_default="",
                default="",
                verbose_name="فصيلة الدم",
            ),
        ),
        migrations.AlterField(
            model_name="healthrecord",
            name="blood_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("A+", "A+"),
                    ("A-", "A-"),
                    ("B+", "B+"),
                    ("B-", "B-"),
                    ("AB+", "AB+"),
                    ("AB-", "AB-"),
                    ("O+", "O+"),
                    ("O-", "O-"),
                ],
                max_length=3,
                verbose_name="فصيلة الدم (قديم)",
            ),
        ),
    ]
