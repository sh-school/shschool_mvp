"""نواةُ نموذج CP-SAT الصلب (V2-S3a، W-20261003-016) — الواجهةُ الثابتة للجلسات الشقيقة.

    built = build_model(inputs)            # inputs: CpSatInputs من operations.cpsat_adapter.build_inputs
    built.model                            # cp_model.CpModel — قيودٌ صلبةٌ فقط، بلا دالّة هدف
    built.x[(i, day, period)]              # BoolVar: الصفُّ i (فهرسُ inputs.demand) في هذه الخانة
    built.vars                             # متغيّراتٌ مساعدة بمفاتيحَ-معرّفات (انظر BuiltModel.vars)
    built.constraint_counts                # {رمزُ القيد: عددُ القيود المضافة} — رمزُه من constraint_registry
    built.var_counts                       # دليلُ حجم النموذج
    add_soft_terms(built, terms)           # نقطةُ امتداد الهدف: terms = [(رمزُ مرن, تعبيرٌ خطّيّ, وزن), ...]

لا أسماءَ في أيّ مفتاحٍ ولا رسالة: معرّفاتٌ فقط (PDPPL، شروطُ 0105). ولا eval ولا pickle.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from ortools.sat.python import cp_model

from operations.cpsat_adapter import CpSatInputs, DemandRow

#: اسمُ الواجهة المتّفقُ عليه مع الجلسات الشقيقة.
SchedulerInputs = CpSatInputs

#: قيودٌ قابلةٌ للإيقاف بوسمٍ (افتراضاتُ مالكٍ لا نواةٌ ولا قفلٌ إداريّ).
TOGGLEABLE = ("HC5", "HC8", "HC11", "HC22")
#: قيودٌ صلبةٌ رتبتُها dense/relaxed في السجلّ (لا جولاتِ استرخاءٍ في V2): قائمةٌ افتراضاً وتُوقَف بوسم `disabled` وحدَه.
RANKED = ("HC14", "HC16B", "HC17", "HC20")


@dataclass(frozen=True)
class ModelOptions:
    """ما يتغيّر بين مدرسةٍ وأخرى — يُبنى مرّةً قبل بناء النموذج ولا استعلامَ في الحلقة."""

    #: سياسةُ المدرسة (`constraint_registry.resolve`)؛ None = افتراضُ الكود. قيدٌ رتبتُه ≠ never يُوقَف.
    policy: Any = None
    #: إيقافٌ صريحٌ بوسم (مثلاً {"HC5"}) فوق السياسة.
    disabled: frozenset[str] = frozenset()
    #: سقفُ الحصّة الأولى لكلّ معلّمٍ أسبوعيّاً (HC22، D-166م) وسقفُ الأخيرة (HC8).
    first_cap: int = 2
    last_cap: int = 2
    #: الشرطُ الثاني في HC8: طرفا المعلّم لا يقعان على شعبةٍ واحدة.
    last_distinct_class: bool = True
    #: أقصى فجوةٍ بالدقائق تُعدّ تلاصقاً (HC5).
    joinable_gap: int = 10
    #: طابقُ كلّ نطاق (لـHC13)؛ فارغٌ = لا حكمَ طابقيّاً مستقلّاً عن HC5.
    band_floor: dict[str, int] = field(default_factory=dict)
    #: HC6 بالقسمة الكاملة (floor ≤ عددُ اليوم ≤ ceil) لا بالسقف وحدَه.
    even_spread: bool = True
    #: HC16: سقفُ اليوم المشتقُّ ⌈النصاب÷أيّام المعلّم⌉ (+1 لمن يدرّس مزدوجة)، وإلّا افتراضُ 5/التفضيل فقط.
    derived_day_cap: bool = True
    #: تخفيفٌ معلَن (قرار المالك 2026-10-09): معلّمون يُرفع عنهم منعُ التلاصق HC5؛ وسقفُ التتابع بعده:
    #: 0 = بلا سقف، 2 = حصتان متتاليتان لا ثلاث. يُسجَّل كلُّ معلّمٍ في `BuiltModel.relaxations`.
    touch_relaxed: frozenset[str] = frozenset()
    touch_relaxed_run_cap: int = 0
    #: قيدٌ صلب بأمر المالك 2026-10-09: لا يقف المعلّم الحصتين السادسة والسابعة معاً في اليوم (يشمل المزدوجات).
    no_6_7: bool = False
    #: سقفُ الأولى (HC22) الأعلى لمعلّمين محدَّدين: ((معلّم، سقف), …) — قرار المالك 2026-10-09 لأنصبة 15 فأكثر.
    first_cap_override: tuple = ()
    #: ثلاثُ حصصٍ بأرقامٍ متتاليةٍ ممنوعةٌ لمن خُفِّف عنهم التلاصق (ولو فصلت فسحةٌ بينها) — أمر المالك 2026-10-09.
    triples_by_number: bool = False
    #: HC9: «time» = عبر النطاقات بالساعة (الافتراضيّ)، «period» = برقم الحصّة كالمرجع.
    resource_by: str = "time"
    #: صفُّ كلّ شعبة («G11»…) — يلزم HC17 ولا يحمله `CpSatInputs`؛ فارغٌ = HC17 لا يعمل (بلا مرجع صفٍّ لا حكم).
    class_grade: dict[str, str] = field(default_factory=dict)
    thursday_pair_grades: frozenset[str] = frozenset({"G11", "G12"})
    #: فجوةٌ اختياريةٌ في مجموع حصص كلّ صفٍّ (استثناءٌ معلَنٌ من «الطلبُ مساواةٌ صلبة»): تتيح طبقةَ «المتعذّرات»
    #: في الهدف المعجميّ. افتراضُه False = المساواةُ كما كانت، فلا يتغيّر نموذجُ أيّ مستدعٍ قائم.
    allow_unplaced: bool = False
    #: يسمّي القيودَ في الـproto (للتنقيح فقط؛ يزيد الذاكرة).
    name_constraints: bool = False

    def enabled(self, code: str) -> bool:
        if code in self.disabled:
            return False
        if self.policy is not None and code in TOGGLEABLE:
            return self.policy.break_at(code) == "never"
        return True


@dataclass
class BuiltModel:
    model: cp_model.CpModel
    inputs: CpSatInputs
    options: ModelOptions
    #: معرّفاتُ الصفوف بالترتيب: «شعبة|مادّة|معلّم|وسمُ المجموعة» (معرّفاتٌ لا أسماء).
    row_ids: list[str] = field(default_factory=list)
    #: متغيّرُ الوضع: (فهرسُ الصفّ، اليوم، رقمُ الحصّة) ← BoolVar.
    x: dict[tuple[int, int, int], cp_model.IntVar] = field(default_factory=dict)
    #: مساعداتٌ بمفاتيحَ-معرّفات:
    #:   ("occ", teacher_id, day, start_min, end_min) ← BoolVar: المعلّمُ مشغولٌ في هذا الفاصل الزمنيّ
    #:   ("first", teacher_id) ← IntVar عددُ الأيّام التي يُدرّس فيها حصّةً أولى
    #:   ("last", teacher_id)  ← IntVar عددُ الأيّام التي يُدرّس فيها آخرَ حصّةٍ متاحةٍ له
    vars: dict[tuple, Any] = field(default_factory=dict)
    constraint_counts: Counter = field(default_factory=Counter)
    var_counts: dict[str, int] = field(default_factory=dict)
    #: من وُسم موقوفاً في هذا البناء (وسمٌ + سياسة).
    disabled: tuple[str, ...] = ()
    #: حدودٌ تُسجَّل للتشخيص (مثلاً HC4_cut_cells، exempt_cut_cells).
    notes: dict[str, int] = field(default_factory=dict)
    #: إرخاءاتُ أرضيّة HC14/HC16B المعلَنة لكلّ معلّم (D-286م): معرّفٌ، حمل، كتل، الأرضيّة الأصليّة والمخفَّفة. «مخفَّف» وسمٌ للجدول.
    relaxations: list[dict] = field(default_factory=list)
    soft_terms: list[tuple[str, Any, float]] = field(default_factory=list)
    #: طبقاتُ الهدف المعجميّ بالترتيب (الأعلى أوّلاً)؛ فارغةٌ = هدفٌ واحدٌ كما كان. يملؤها `add_layers`.
    layers: list[tuple[str, Any]] = field(default_factory=list)

    @property
    def rows(self) -> list[DemandRow]:
        return self.inputs.demand


def row_id(row: DemandRow) -> str:
    return f"{row.cls}|{row.subj}|{row.teacher}|{row.elec}"


def build_model(inputs: CpSatInputs, options: ModelOptions | None = None) -> BuiltModel:
    """يبني النموذجَ الصلب كاملاً من مدخلات `build_inputs`. لا دالّةَ هدفٍ هنا (انظر `add_soft_terms`)."""
    from . import hard_constraints

    options = options or ModelOptions()
    built = BuiltModel(
        model=cp_model.CpModel(),
        inputs=inputs,
        options=options,
        row_ids=[row_id(r) for r in inputs.demand],
    )
    hard_constraints.add_all(built)
    proto = built.model.Proto()
    built.var_counts = {
        "bool_x": len(built.x),
        "variables": len(proto.variables),
        "constraints": len(proto.constraints),
    }
    built.disabled = tuple(c for c in TOGGLEABLE if not options.enabled(c))
    return built


def add_soft_terms(built: BuiltModel, terms: Iterable[tuple[str, Any, float]]) -> int:
    """نقطةُ امتدادٍ للهدف المرن: كلُّ حدٍّ (رمزُ المرن، تعبيرٌ خطّيّ، وزن). يُراكم الحدودَ ويُعيد تعريفَ التصغير.

    تُرجع عددَ الحدود الكليّ. (`objective.py` يملك اشتقاقَ الحدود؛ هنا التجميعُ وحدَه.)
    """
    built.soft_terms.extend(terms)
    if built.soft_terms:
        built.model.Minimize(sum(weight * expr for _code, expr, weight in built.soft_terms))
    return len(built.soft_terms)


def unplaced_total(built: BuiltModel) -> Any:
    """مجموعُ المتعذّرات (حصصٌ لم توضع) — صفرٌ ثابتٌ حين لا فجوة (`allow_unplaced` مطفأ)."""
    gaps = [v for key, v in built.vars.items() if key[0] == "unplaced"]
    return sum(gaps) if gaps else 0


def add_layers(built: BuiltModel, layers: Iterable[tuple[str, Any]]) -> int:
    """يسجّل طبقاتِ الهدف المعجميّ (اسمٌ، تعبيرٌ) من الأعلى. الحلُّ المتتالي في المشغّل (`runner.solve`)."""
    built.layers = list(layers)
    return len(built.layers)


__all__ = [
    "BuiltModel",
    "ModelOptions",
    "SchedulerInputs",
    "TOGGLEABLE",
    "add_layers",
    "add_soft_terms",
    "build_model",
    "row_id",
    "unplaced_total",
]
