"""مصدرٌ جديد: خرج بإذن المعلّم ولم يعد حتى نهاية الحصّة."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("operations", "0049_class_exit")]

    operations = [
        migrations.AlterField(
            model_name="studentattendance",
            name="source",
            field=models.CharField(
                choices=[
                    ("teacher", "معلّم الحصّة"),
                    ("supervisor", "مشرف الجناح"),
                    ("gate", "ملاحظ الطلبة"),
                    ("clinic", "العيادة"),
                    ("system", "النظام"),
                    ("teacher_late", "نقرةُ المعلّم — دخل متأخّراً"),
                    ("teacher_out", "نقرةُ المعلّم — خرج بإذنٍ ولم يعد"),
                ],
                db_index=True,
                default="teacher",
                max_length=12,
                verbose_name="المصدر",
            ),
        ),
    ]
