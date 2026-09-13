"""مصدرٌ جديدٌ لسجلّ الحضور: نقرةُ المعلّم «دخل متأخّراً» (قرارُ 2026-09-13)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("operations", "0047_period_confirmation")]

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
                ],
                db_index=True,
                default="teacher",
                max_length=12,
                verbose_name="المصدر",
            ),
        ),
    ]
