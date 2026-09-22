"""فهرسٌ جزئيٌّ على `StudentAttendance.exit` — يُبنى دون قفل الكتابة على الجدول.

حذفُ خروجٍ يُفرغ العمودَ (`SET_NULL`) ويفحصه قيدُ المفتاح عند الإيداع؛ وبلا فهرسٍ
يمسحان سجلَّ الحضور كلَّه. والسطورُ غيرُ الفارغة قليلة، فالفهرسُ صغير. و`CONCURRENTLY`
لا يجري داخل معاملة — فالهجرةُ بلا معاملة، وعمليّتُها واحدة.
"""

from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("operations", "0054_attendance_exit_provenance"),
    ]

    operations = [
        AddIndexConcurrently(
            model_name="studentattendance",
            index=models.Index(
                condition=models.Q(("exit__isnull", False)),
                fields=["exit"],
                name="attendance_exit_accounted",
            ),
        ),
    ]
