"""
مستوياتُ تقييم الأداء الخمسة بعتبات المادة 16، ووسمُ الفترتين.

المادة 16 من النظام الوظيفي لموظفي المدارس (قرار مجلس الوزراء 32/2019)،
«02- النظام الوظيفي لموظفي المدارس.pdf» صفحتا الملفّ 10–11: ممتاز 90 فأعلى،
جيد جداً أعلى من 75 إلى أقل من 90، جيد أعلى من 65 إلى 75، مقبول من 50 إلى 65،
ضعيف أقل من 50. وكانت المنصّةُ أربعَ درجاتٍ بعتبات 90/75/60 و«يحتاج تطوير».

الترحيلُ يعيد حسابَ `rating` لكلّ صفٍّ من `total_score` المخزَّن (العددُ الصحيح
هو ما بقي من الماضي — ولا فرقَ بين القراءتين عند الأعداد الصحيحة). وتكرارُه لا
يغيّر شيئاً، وعكسُه يعيد العتباتِ القديمة.
"""

from django.db import migrations, models


def _five_levels(total):
    if total >= 90:
        return "excellent"
    if total > 75:
        return "very_good"
    if total > 65:
        return "good"
    if total >= 50:
        return "acceptable"
    return "weak"


def _four_levels(total):
    if total >= 90:
        return "excellent"
    if total >= 75:
        return "very_good"
    if total >= 60:
        return "good"
    return "needs_dev"


def _recompute(rule):
    def run(apps, schema_editor):
        EmployeeEvaluation = apps.get_model("quality", "EmployeeEvaluation")
        for ev in EmployeeEvaluation.objects.exclude(rating="").only("pk", "total_score", "rating"):
            new = rule(ev.total_score)
            if new != ev.rating:
                EmployeeEvaluation.objects.filter(pk=ev.pk).update(rating=new)

    return run


PERIODS = [
    ("S1", "متابعة منتصف العام (داخليّة، غير وزاريّة)"),
    ("S2", "التقرير السنويّ (الوزاريّ)"),
]


class Migration(migrations.Migration):
    dependencies = [
        ("quality", "0017_alter_classroomobservation_kind"),
    ]

    operations = [
        migrations.AlterField(
            model_name="employeeevaluation",
            name="rating",
            field=models.CharField(
                blank=True,
                choices=[
                    ("excellent", "ممتاز (100–90)"),
                    ("very_good", "جيد جداً (89–76)"),
                    ("good", "جيد (75–66)"),
                    ("acceptable", "مقبول (65–50)"),
                    ("weak", "ضعيف (أقل من 50)"),
                ],
                max_length=15,
            ),
        ),
        migrations.AlterField(
            model_name="employeeevaluation",
            name="period",
            field=models.CharField(choices=PERIODS, max_length=2, verbose_name="الفترة"),
        ),
        migrations.AlterField(
            model_name="evaluationcycle",
            name="period",
            field=models.CharField(choices=PERIODS, max_length=2),
        ),
        migrations.RunPython(_recompute(_five_levels), _recompute(_four_levels)),
    ]
