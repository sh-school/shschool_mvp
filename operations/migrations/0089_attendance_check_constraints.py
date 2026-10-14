"""قيدا CHECK على الغياب (W-20261004-021): لا عودةَ قبل الخروج، ولا مدىً معكوسَ لعذر. الجدولان صغيران (الإنتاج: 297 خروجاً) فلا قفلَ يُذكر."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0088_clean_attendance_constraint_violators"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="absenceexcuse",
            constraint=models.CheckConstraint(
                condition=models.Q(("date_from__lte", models.F("date_to"))),
                name="absence_excuse_range_ordered",
            ),
        ),
        migrations.AddConstraint(
            model_name="classexit",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("returned_at__isnull", True),
                    ("returned_at__gte", models.F("left_at")),
                    _connector="OR",
                ),
                name="class_exit_returned_after_left",
            ),
        ),
    ]
