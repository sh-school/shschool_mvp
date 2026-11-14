from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0097_teacherperiodpreference"),
    ]

    operations = [
        migrations.AlterField(
            model_name="classexit",
            name="destination",
            field=models.CharField(
                choices=[
                    ("clinic", "العيادة"),
                    ("restroom", "دورة المياه"),
                    ("sa_coord", "منسق شؤون الطلاب"),
                    ("wing_sup", "مشرف الجناح"),
                    ("vice", "النائب الإداري"),
                    ("arts", "الفنون البصرية"),
                    ("lab_cs", "معمل الحاسوب"),
                    ("lab_sci", "معمل العلوم"),
                    ("pe", "التربية البدنية"),
                    ("school", "الخروج من المدرسة"),
                    ("admin", "الإدارة / المشرف"),
                    ("other", "أخرى"),
                ],
                default="restroom",
                max_length=10,
                verbose_name="الوجهة",
            ),
        ),
    ]
