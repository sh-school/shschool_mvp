"""objective.py — أوزانُ القيود المرنة ودالّةُ الهدف لـV2 (V2-S3، W-20261003-016).

    الهدفُ = Σ وزنُ(k) × مخالفات(k)   على القيود المرنة الثلاثةَ عشر — يُصغَّر.

**من الصفر.** لا حدَّ فيه يقيس البُعدَ عن جدولٍ قائم: قرارُ المالك 2026-10-01 باستبدال
الجدول كاملاً أبطل «تصغيرَ الحركة» التي كان النموذجُ المرجعيُّ يصغّرها.

**الأوزانُ بياناتٌ لا شيفرة، ومحصورةٌ مرّتين:**
  · مفاتيحُها تعدادٌ مغلقٌ هو مفاتيحُ `constraint_registry.SOFT_CONSTRAINTS` — مفتاحٌ
    مجهولٌ يُرفض بالاسم (لا يُتجاهَل بصمت فيضيع ضبطٌ كتبه أحدٌ ولم يُطبَّق).
  · قيمتُها عددٌ صحيحٌ ضمن مدًى: العقوبةُ في [0, 100] والمكافأةُ (`double_bonus`،
    `first_period_floor`) في [−100, 0] — فلا ينقلب قيدٌ من عقوبةٍ إلى مكافأةٍ بخطأ إشارة.
    والسقفُ 100 ضعفا أثقلِ وزنٍ قائم (`core_early`=30 ⇒ ثلاثةُ أضعافٍ بهامش)؛ يُراجَع بقرار.
  · تُقرأ من `dict` أو من JSON بـ`json.loads` وحده (لا eval ولا pickle).

الواجهةُ مع `model.py` (v2-core) عقدُ `BuiltModelView`؛ والنقطةُ الموعودةُ
`add_soft_terms(built, terms)` تستقبل `SoftObjective.terms` (تعبيراً لكلّ مفتاحٍ مضروباً
في وزنه) و`SoftObjective.total` (المجموع). أو يُستدعى `apply(model)` فيُصغِّر المجموع.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..constraint_registry import SOFT_CONSTRAINTS
from .soft_constraints import SOFT_KEYS, BuiltModelView, build_terms, evaluate_placements

if TYPE_CHECKING:
    from ortools.sat.python import cp_model

#: الأوزانُ الافتراضيّةُ = سجلُّ المنصّة اليوم (المصدرُ الواحد) — أعدادٌ صحيحةٌ كلُّها.
DEFAULT_WEIGHTS: dict[str, int] = {s.code: int(s.weight) for s in SOFT_CONSTRAINTS}

#: القيودُ التي وزنُها مكافأةٌ (≤ 0). ما سواها عقوبةٌ (≥ 0). يحرسه اختبارٌ على الافتراضيّات.
BONUS_KEYS: frozenset[str] = frozenset(k for k, w in DEFAULT_WEIGHTS.items() if w < 0)

MAX_WEIGHT = 100


class WeightError(ValueError):
    """وزنٌ غيرُ صالح: مفتاحٌ مجهولٌ أو قيمةٌ ليست عدداً صحيحاً أو خارجَ المدى أو بإشارةٍ مقلوبة."""


def weight_range(key: str) -> tuple[int, int]:
    return (-MAX_WEIGHT, 0) if key in BONUS_KEYS else (0, MAX_WEIGHT)


def validate_weights(raw: Mapping[str, object] | None) -> dict[str, int]:
    """الأوزانُ الفعليّةُ: الافتراضُ مُعدَّلاً بـ`raw`، بعد التحقّق. لا يُغيّر `raw`."""
    weights = dict(DEFAULT_WEIGHTS)
    for key, value in (raw or {}).items():
        if key not in DEFAULT_WEIGHTS:
            raise WeightError(f"قيدٌ مرنٌ مجهول: {key!r} (المسموح: {', '.join(SOFT_KEYS)})")
        # bool ابنُ int في بايثون — `True` ليس وزناً.
        if isinstance(value, bool) or not isinstance(value, int):
            raise WeightError(f"وزنُ {key} يجب أن يكون عدداً صحيحاً لا {value!r}")
        low, high = weight_range(key)
        if not low <= value <= high:
            raise WeightError(f"وزنُ {key}={value} خارجَ المدى [{low}, {high}]")
        weights[key] = value
    return weights


def weights_from_json(text: str) -> dict[str, int]:
    """من نصّ JSON فقط — كائنٌ مسطّحٌ {مفتاح: عدد}."""
    data = json.loads(text)
    if not isinstance(data, dict):
        raise WeightError("الأوزانُ يجب أن تكون كائنَ JSON {مفتاح: عدد}")
    return validate_weights(data)


@dataclass
class SoftObjective:
    """الهدفُ مبنيّاً على نموذج: تعبيرٌ مضروبٌ في وزنه لكلّ قيد، ومجموعُها."""

    weights: dict[str, int]
    #: تعبيرُ المخالفات بلا وزن (للتقرير والمقارنة بالمقيِّم).
    units: dict[str, object]
    terms: dict[str, object]
    total: object

    def apply(self, model: cp_model.CpModel) -> None:
        model.Minimize(self.total)

    def breakdown(self, solver: cp_model.CpSolver) -> dict[str, int]:
        """عدّادُ مخالفات كلّ قيدٍ في حلٍّ مُحقَّق — بوحدة القيد لا بعد الوزن."""
        return {k: int(solver.Value(expr)) for k, expr in self.units.items()}


def build_objective(
    built: BuiltModelView,
    pedagogy: Mapping[str, str],
    weights: Mapping[str, object] | None = None,
) -> SoftObjective:
    """يبني الهدفَ على `built`. لا يستدعي `Minimize` — القرارُ لمن يملك النموذج (`apply`)."""
    from ortools.sat.python import cp_model

    w = validate_weights(weights)
    units = build_terms(built, pedagogy)
    terms = {k: w[k] * units[k] for k in SOFT_KEYS}
    return SoftObjective(w, units, terms, cp_model.LinearExpr.Sum(list(terms.values())))


def weighted_cost(units: Mapping[str, int], weights: Mapping[str, object] | None = None) -> int:
    """كلفةٌ على عدّاد مخالفاتٍ جاهز (من `evaluate_placements`) — بلا حلّال."""
    w = validate_weights(weights)
    return sum(w[k] * int(units.get(k, 0)) for k in SOFT_KEYS)


__all__ = [
    "BONUS_KEYS",
    "DEFAULT_WEIGHTS",
    "MAX_WEIGHT",
    "SoftObjective",
    "WeightError",
    "build_objective",
    "evaluate_placements",
    "validate_weights",
    "weight_range",
    "weighted_cost",
    "weights_from_json",
]
