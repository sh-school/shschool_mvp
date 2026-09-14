"""
quality/evaluation_services.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
حفظُ تقييم أداء الموظّف — المسارُ الوحيد الذي يكتب الدرجاتِ والتقدير.

يستدعيه `quality.evaluation_views.create_evaluation`، وفيه يُفحص قيدُ الجزاء قبل
أيّ كتابة: من عليه جزاءٌ تأديبيٌّ لا يُكتب له «ممتاز» ولا «جيد جداً».

المرجع: `AAdocs/ministry_data/2026_2027/06_attendance_performance_review.md` §2.1
(المادتان 17 و18، مكرّرتان حرفيّاً في الاستمارات السبع):
  - المادة 17: «لا يجوز تقييم أداء الموظفين من الفئات المبيّنة فيما يلي بمستوى ممتاز»
  - المادة 18: «… بمستوى ممتاز أو جيد جداً»
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from django.db import transaction

from .models import EmployeeEvaluation, EvaluationScore

if TYPE_CHECKING:
    from core.models import CustomUser

#: (مفتاح المحور، اسمه، درجته القصوى) — كما يبنيها `_get_axes_for_employee`.
AxisSpec = tuple[str, str, int]

DEFAULT_AXIS_FIELDS = frozenset(EmployeeEvaluation._AXIS_FIELDS)
#: التقديرُ الذي يحجبه الجزاء. المادة 17 تحجب «ممتاز» وحده لجزاءٍ أخفّ، والمادة 18
#: تحجب الاثنين لجزاءٍ أشدّ؛ والتمييزُ بين الدرجتين يحتاج سجلَّ الجزاءات (2.1) —
#: فإلى أن يُبنى، أيُّ جزاءٍ نشطٍ يحجب الاثنين (الأحوط).
SANCTION_BARRED_RATINGS = frozenset({"excellent", "very_good"})
_EVALUATOR_STATUSES = frozenset({"draft", "submitted"})


class EvaluationRejectedError(ValueError):
    """تقييمٌ لا يُحفظ — الرسالةُ تُعرض للمقيِّم كما هي."""


def has_active_sanction(staff: CustomUser, academic_year: str) -> bool:
    """
    هل على الموظّف جزاءٌ تأديبيٌّ خلال عام التقييم؟

    يُربط بـ2.1 — `StaffDisciplinaryAction` غير موجود بعد، فلا مصدرَ للجزاءات
    يُقرأ منه، والدالّةُ تُرجع False. وهي نقطةُ التعليق الوحيدة: `save_evaluation`
    يستدعيها قبل الكتابة، فحين يُبنى السجلُّ يكفي أن يُقرأ منه هنا.
    """
    return False


def parse_axis_scores(axes: Sequence[AxisSpec], data: Mapping[str, str]) -> dict[str, int]:
    """درجةُ كلّ محورٍ عددٌ صحيحٌ بين الصفر وحدِّه — وإلّا رُفض التقييم كلُّه."""
    scores: dict[str, int] = {}
    for key, label, max_score in axes:
        raw = (data.get(key) or "0").strip()
        try:
            value = int(raw)
        except ValueError:
            raise EvaluationRejectedError(f"«{label}»: الدرجةُ عددٌ صحيح") from None
        if not 0 <= value <= max_score:
            raise EvaluationRejectedError(f"«{label}»: الدرجةُ بين 0 و{max_score}")
        scores[key] = value
    return scores


def _uses_default_axes(axes: Sequence[AxisSpec]) -> bool:
    return {key for key, _label, _max in axes} <= DEFAULT_AXIS_FIELDS


def _weighted_total(evaluation: EmployeeEvaluation, evaluator: CustomUser, own_total: int) -> int:
    """المجموعُ المرجَّح كما يحسبه `calculate_weighted_total` — بدرجات هذا المقيِّم الجديدة."""
    own_weight = 100
    pairs: list[tuple[int, int]] = []
    for score in evaluation.scores.all():
        if score.evaluator_id == evaluator.pk:
            own_weight = score.weight
        else:
            pairs.append((score.total_score, score.weight))
    pairs.append((own_total, own_weight))
    total_weight = sum(w for _t, w in pairs)
    return round(sum(t * w for t, w in pairs) / total_weight) if total_weight else own_total


@transaction.atomic
def save_evaluation(
    *,
    evaluation: EmployeeEvaluation,
    evaluator: CustomUser,
    axes: Sequence[AxisSpec],
    data: Mapping[str, str],
) -> EmployeeEvaluation:
    """
    يحفظ درجاتِ المقيِّم وملاحظاتِه وحالةَ التقييم، أو يرفع `EvaluationRejectedError`
    ولا يكتب شيئاً.

    المحاورُ الافتراضيّةُ الأربعة حقولٌ على التقييم نفسه. ومحاورُ قالب الدور
    (الاستمارات الوزاريّة) لا حقولَ لها، فتُحفظ في `EvaluationScore.custom_axes`
    لهذا المقيِّم، ويُحسب المجموعُ مرجَّحاً على المقيِّمين — وكانت تُرمى قبل ذلك
    فيُحفظ التقييمُ صفراً.
    """
    status = data.get("action", "draft")
    if status not in _EVALUATOR_STATUSES:
        raise EvaluationRejectedError("حالةُ التقييم مسودّةٌ أو مُقدَّمٌ فقط")
    scores = parse_axis_scores(axes, data)

    if _uses_default_axes(axes):
        for key, value in scores.items():
            setattr(evaluation, key, value)
        evaluation.calculate_total()
    else:
        evaluation.total_score = _weighted_total(evaluation, evaluator, sum(scores.values()))
        evaluation.rating = EmployeeEvaluation.rating_for(evaluation.total_score)

    if evaluation.rating in SANCTION_BARRED_RATINGS and has_active_sanction(
        evaluation.employee, evaluation.academic_year
    ):
        raise EvaluationRejectedError(
            f"لا يجوز تقديرُ «{evaluation.get_rating_display()}» لموظّفٍ عليه جزاءٌ "
            "تأديبيٌّ خلال عام التقييم — المادتان 17 و18."
        )

    evaluation.strengths = data.get("strengths", "")
    evaluation.improvements = data.get("improvements", "")
    evaluation.goals_next = data.get("goals_next", "")
    evaluation.status = status
    evaluation.evaluator = evaluator

    if _uses_default_axes(axes):
        evaluation.save()
        return evaluation

    EvaluationScore.objects.update_or_create(
        evaluation=evaluation, evaluator=evaluator, defaults={"custom_axes": scores}
    )
    # `update_fields` بلا حقول المحاور الافتراضيّة: فلا يُعيد `save()` الحسابَ منها
    # فيمحو المجموعَ المرجَّح.
    evaluation.save(
        update_fields=[
            "total_score",
            "rating",
            "strengths",
            "improvements",
            "goals_next",
            "status",
            "evaluator",
            "updated_at",
        ]
    )
    return evaluation


def axis_values(
    evaluation: EmployeeEvaluation, evaluator: CustomUser, axes: Sequence[AxisSpec]
) -> dict[str, int]:
    """قيمُ المحاور المعروضة في النموذج: من الحقول، أو من درجات هذا المقيِّم في القالب."""
    if _uses_default_axes(axes):
        return {key: getattr(evaluation, key) or 0 for key, _l, _m in axes}
    own = evaluation.scores.filter(evaluator=evaluator).first() if evaluation.pk else None
    custom = own.custom_axes if own else {}
    return {key: int(custom.get(key, 0)) for key, _l, _m in axes}
