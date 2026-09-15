"""
مستوياتُ تقييم الأداء الخمسة بعتبات المادة 16، ووسمُ الفترتين.

المادة 16 من النظام الوظيفي لموظفي المدارس (قرار مجلس الوزراء 32/2019)،
«02- النظام الوظيفي لموظفي المدارس.pdf» صفحتا الملفّ 10–11: ممتاز 90 فأعلى،
جيد جداً أعلى من 75 إلى أقل من 90، جيد أعلى من 65 إلى 75، مقبول من 50 إلى 65،
ضعيف أقل من 50. وكانت المنصّةُ أربعَ درجاتٍ بعتبات 90/75/60 و«يحتاج تطوير».

الترحيلُ يعيد حسابَ `rating` لكلّ صفٍّ كما يحسبه النموذج (`EmployeeEvaluation.save`):
  - تقييمٌ على قالبٍ بدرجات مقيِّمين: من المجموع المرجَّح **غير المقرَّب** — لا من
    `total_score` المقرَّب، فـ89.5 المخزَّنُ 90 «جيد جداً» لا «ممتاز». ويُكتب `total_score`
    داخل نطاق مستواه (`EmployeeEvaluation.total_for`).
  - غيرُه: من `total_score` (العددُ الصحيح هو المجموعُ نفسُه).
  - مسودّةٌ فارغة (لا درجةَ ولا مقيِّم — ما كان GET القديم يُنشئه عند فتح النموذج):
    `rating` فارغ، لا «ضعيف». المستوى اسمٌ وزاريٌّ تترتّب عليه آثارُ المادتين 21 و22.
وتكرارُه لا يغيّر شيئاً، وعكسُه يعيد العتباتِ القديمة من `total_score`.
"""

import math
from collections.abc import Callable
from fractions import Fraction
from typing import Any

from django.db import migrations, models

_AXES = ("axis_professional", "axis_commitment", "axis_teamwork", "axis_development")


def _five_levels(total: int | Fraction) -> str:
    if total >= 90:
        return "excellent"
    if total > 75:
        return "very_good"
    if total > 65:
        return "good"
    if total >= 50:
        return "acceptable"
    return "weak"


def _four_levels(total: int) -> str:
    if total >= 90:
        return "excellent"
    if total >= 75:
        return "very_good"
    if total >= 60:
        return "good"
    return "needs_dev"


def _weighted(evaluation: Any, score_model: Any) -> Fraction | None:
    """المجموعُ المرجَّح غير المقرَّب كما في `calculate_weighted_total`، أو None."""
    if evaluation.template_id is None:
        return None
    weighted = weight_sum = 0
    for score in score_model.objects.filter(evaluation_id=evaluation.pk):
        custom = score.custom_axes or {}
        total = sum(custom.values()) if custom else sum(getattr(score, f) for f in _AXES)
        weighted += total * score.weight
        weight_sum += score.weight
    return Fraction(weighted, weight_sum) if weight_sum else None


def _shown(exact: Fraction) -> int:
    """`EmployeeEvaluation.total_for`: الأقربُ داخل نطاق المستوى."""
    rounded = round(exact)
    if _five_levels(rounded) == _five_levels(exact):
        return int(rounded)
    return math.floor(exact) if rounded > exact else math.ceil(exact)


def _is_blank(evaluation: Any, score_model: Any) -> bool:
    return (
        evaluation.status == "draft"
        and not evaluation.total_score
        and not any(getattr(evaluation, f) for f in _AXES)
        and not score_model.objects.filter(evaluation_id=evaluation.pk).exists()
    )


def forward(apps: Any, schema_editor: Any) -> None:
    EmployeeEvaluation = apps.get_model("quality", "EmployeeEvaluation")
    EvaluationScore = apps.get_model("quality", "EvaluationScore")
    for ev in EmployeeEvaluation.objects.all().iterator():
        total = ev.total_score
        if _is_blank(ev, EvaluationScore):
            rating = ""
        else:
            exact = _weighted(ev, EvaluationScore)
            if exact is not None:
                total = _shown(exact)
            rating = _five_levels(exact if exact is not None else total)
        if (total, rating) != (ev.total_score, ev.rating):
            EmployeeEvaluation.objects.filter(pk=ev.pk).update(total_score=total, rating=rating)


def _recompute(rule: Callable[[int], str]) -> Callable[[Any, Any], None]:
    def run(apps: Any, schema_editor: Any) -> None:
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
        migrations.RunPython(forward, _recompute(_four_levels)),
    ]
