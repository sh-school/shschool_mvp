"""
التظلّمُ من تقرير تقييم الأداء — المادة 20 (02_staff_affairs.md:211): تاريخُ تقديمه
إلى لجنة موظفي المدارس، وتاريخُ إخطار الموظّف بقرارها. منهما ومن «تاريخ العلم»
(`acknowledged_at`) تُحسب نهائيّةُ التقرير (`EmployeeEvaluation.is_final`).
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("quality", "0018_employeeevaluation_five_level_rating"),
    ]

    operations = [
        migrations.AddField(
            model_name="employeeevaluation",
            name="grievance_submitted_on",
            field=models.DateField(
                blank=True, null=True, verbose_name="تاريخ تقديم التظلّم إلى لجنة موظفي المدارس"
            ),
        ),
        migrations.AddField(
            model_name="employeeevaluation",
            name="grievance_decided_on",
            field=models.DateField(
                blank=True, null=True, verbose_name="تاريخ إخطار الموظّف بقرار اللجنة"
            ),
        ),
    ]
