from django.db import migrations, models


class Migration(migrations.Migration):
    """توسيعٌ فقط (W-20261002-020): عمودٌ يقبل NULL يحمل وسمَ «تصحيحٌ دون معاينة» — لا يمسّ قراءةً ولا كتابةً قائمة."""

    dependencies = [
        ("operations", "0063_attendance_ledger_guards"),
    ]

    operations = [
        migrations.AddField(
            model_name="studentattendance",
            name="unobserved_correction",
            field=models.JSONField(
                blank=True, null=True, verbose_name="تصحيحٌ دون معاينة"
            ),
        ),
    ]
