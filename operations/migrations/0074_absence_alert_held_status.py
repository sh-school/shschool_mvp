"""حالتان جديدتان لتنبيه الغياب: «بانتظار الإصدار» (held) و«قيد الإصدار» (issuing، وسيطةٌ لا يلتقطها المرسِلُ الجماعيّ) — D-246م: لا إرسالَ لوليّ الأمر إلا بزرّ حاصر الغياب.

تغييرُ خيارات الحقل فقط: لا SQL ولا بياناتٌ تُمسّ ولا حذفٌ ولا إعادةُ تسمية؛ والعكسُ تغييرُ خياراتٍ كذلك.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0073_class_grid_constraints"),
    ]

    operations = [
        migrations.AlterField(
            model_name="absencealert",
            name="status",
            field=models.CharField(
                choices=[
                    ("held", "بانتظار الإصدار"),
                    ("issuing", "قيد الإصدار"),
                    ("pending", "قيد المراجعة"),
                    ("notified", "تم الإبلاغ"),
                    ("resolved", "تم الحل"),
                ],
                db_index=True,
                default="pending",
                max_length=10,
                verbose_name="الحالة",
            ),
        ),
    ]
