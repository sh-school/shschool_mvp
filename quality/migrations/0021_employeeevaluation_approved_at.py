"""
لحظةُ اعتماد المدير للتقرير — حدُّ تاريخ الاستلام الأدنى.

«يضع الرئيس المباشر تقييم أداء الموظف ويعتمد من مدير المدرسة» (المادة 16)، و«يُعلن الموظف
بنسخة من تقرير تقييم الأداء، ويجوز للموظف أن يتظلم منه ... خلال خمسة عشر يوماً من تاريخ
علمه» (المادة 20) — «02- النظام الوظيفي لموظفي المدارس.pdf» صفحتا الملفّ 10 و12.

فلا يُعلَم الموظّفُ بتقريرٍ قبل اعتماده، وكان تاريخُ الاستلام المدوَّن يقبل أيَّ ماضٍ، فيصير
التقريرُ نهائيّاً فورَ تدوينه. والصفوفُ المعتمَدةُ قبل هذا الحقل تبقى بلا لحظةِ اعتماد،
فحدُّها لحظةُ إنشاء التقرير (`created_at`) — انظر `record_receipt_on_refusal`.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("quality", "0020_employeeevaluation_receipt_and_minister_approval"),
    ]

    operations = [
        migrations.AddField(
            model_name="employeeevaluation",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="تاريخ اعتماد المدير"),
        ),
    ]
