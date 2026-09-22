"""
تاريخا المادة 20 الباقيان، وحمايةُ ربط التقييم بقالبه.

- `grievance_decision_approved_on`: «ويكون قرار اللجنة في التظلم نهائياً بعد اعتماده من
  الوزير» («02- النظام الوظيفي لموظفي المدارس.pdf» صفحة الملفّ 13، المطبوعة 27).
- `received_on`: «تاريخ استلام الموظف (يرجى تدوين التاريخ في حالة رفض الموظف التوقيع)»
  («استمارة تقييم المعلم والدليل التفسيري.pdf» ص2) — تاريخُ العلم عند رفض الإقرار.
- `template` بـRESTRICT: حذفُ قالبٍ عليه تقييماتٌ كان يُفرغ الربطَ فتسقط درجاتُه من المجموع.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("quality", "0019_employeeevaluation_grievance_dates"),
    ]

    operations = [
        migrations.AddField(
            model_name="employeeevaluation",
            name="grievance_decision_approved_on",
            field=models.DateField(
                blank=True, null=True, verbose_name="تاريخ اعتماد الوزير لقرار اللجنة في التظلّم"
            ),
        ),
        migrations.AddField(
            model_name="employeeevaluation",
            name="received_on",
            field=models.DateField(
                blank=True, null=True, verbose_name="تاريخ استلام الموظف (عند رفضه التوقيع)"
            ),
        ),
        migrations.AlterField(
            model_name="employeeevaluation",
            name="template",
            field=models.ForeignKey(
                blank=True,
                help_text="يُحدَّد تلقائياً حسب دور الموظف. null = المحاور الافتراضية",
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="evaluations",
                to="quality.roleevaluationtemplate",
                verbose_name="قالب التقييم",
            ),
        ),
    ]
