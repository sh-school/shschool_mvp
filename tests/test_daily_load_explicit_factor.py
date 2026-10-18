"""السقفُ اليوميُّ «الصريح» وحدَه يُضاعَف وزنُه (W-20261012-025، بلاغُ قياس W-20261011-008).

حقلُ `max_daily_periods` لا يقبل الفراغ وافتراضُه 5، والشاشةُ تكتب 5 لمن لم يختر، و`get_or_create`
ينشئ الصفَّ بـ5 لمجرّد فتح الصفحة. فكان حفظُ أيِّ تفضيلٍ — فجوةٍ أو تتابعٍ أو ملاحظة — يضاعف وزنَ
حِمل المعلّم اليوميّ في الحلّال والمُقيِّم معاً، فيتغيّر التوليدُ دون علمه.

والإصلاحُ في القراءة لا في الكتابة ولا هجرة: الـ5 المخزَّنةُ «لم يقرّر»، ومن اختارها حقّاً لا يختلف
أثرُه عن الافتراض. والسقفُ الصلبُ نفسُه (`hard_constraints`) لا يتغيّر — يتغيّر وزنُ الجزاء الناعم وحده.
"""

from types import SimpleNamespace

import pytest

from operations.cpsat_adapter import CpSatInputs, DemandRow, TeacherPref
from operations.scheduler_constraints import daily_load_weight
from operations.scheduler_v2 import soft_constraints as sc
from operations.scheduling_limits import (
    DEFAULT_MAX_DAILY,
    EXPLICIT_PREFERENCE_FACTOR,
    is_explicit_daily_cap,
)

cp_model = pytest.importorskip("ortools.sat.python.cp_model")

#: يومٌ عاديٌّ بحصصه السبع — والمعلّمُ فيها كلِّها يومَ الأحد، فوق كلّ سقفٍ مجرَّب (4 و5 و6).
TIMES = {
    1: (430, 480),
    2: (480, 530),
    3: (530, 575),
    4: (600, 650),
    5: (650, 695),
    6: (695, 740),
    7: (760, 810),
}
SUNDAY = 0
AVAILABLE = frozenset((0, day, period) for day in range(5) for period in TIMES)
LOADED_DAY = frozenset((0, SUNDAY, period) for period in TIMES)


def _pref(cap):
    """صفُّ تفضيلٍ بسقفٍ وحده — كما يحفظه معلّمٌ غيّر حقلاً آخرَ وترك السقفَ على حاله."""
    return TeacherPref("T1", cap, None, None, None)


def _inputs(pref):
    inputs = CpSatInputs()
    inputs.class_band = {"C1": "B"}
    inputs.class_level = {"C1": "prep"}
    inputs.bell = {"B|regular": {"periods": list(TIMES), "touch": []}}
    inputs.times = {"B|regular": TIMES}
    inputs.demand = [DemandRow("C1", "RG", "T1", "", len(TIMES))]
    inputs.prefs = {"T1": pref} if pref else {}
    return inputs


def _evaluator_units(pref) -> int:
    """جزاءُ الحِمل بالمقيِّم المستقلّ (`evaluate_placements`) على اليوم العامر."""
    return sc.evaluate_placements(_inputs(pref), {}, LOADED_DAY, AVAILABLE)["daily_load"]


def _solver_units(pref) -> int:
    """جزاءُ الحِمل بترميز CP-SAT نفسِه، والجدولُ مُثبَّت فلا يبقى للحلّال إلّا المتغيّراتُ المساعدة."""
    model = cp_model.CpModel()
    x = {key: model.NewBoolVar("") for key in AVAILABLE}
    for key, var in x.items():
        model.Add(var == int(key in LOADED_DAY))
    built = SimpleNamespace(model=model, x=x, inputs=_inputs(pref))
    model.Minimize(sc.daily_load(sc.SoftContext(built, {})))
    solver = cp_model.CpSolver()
    assert solver.Solve(model) == cp_model.OPTIMAL
    return round(solver.ObjectiveValue())


def test_only_a_cap_other_than_the_default_is_explicit():
    cases = (None, DEFAULT_MAX_DAILY, 4, 6)

    assert [is_explicit_daily_cap(value) for value in cases] == [False, False, True, True]


@pytest.mark.parametrize("units", [_solver_units, _evaluator_units], ids=["solver", "evaluator"])
def test_a_stored_default_weighs_like_no_preference_row(units):
    """الـ5 المخزَّنةُ مثلُ غياب الصفّ: عاملٌ واحدٌ لا اثنان."""
    assert units(_pref(DEFAULT_MAX_DAILY)) == units(None)


def test_the_v1_evaluator_does_not_double_a_row_that_decided_no_cap():
    over_the_default = DEFAULT_MAX_DAILY + 1
    default = daily_load_weight(over_the_default, None)

    assert daily_load_weight(over_the_default, {"max_daily": DEFAULT_MAX_DAILY}) == default
    # صفٌّ فيه حقلٌ آخرُ ولا سقف — كان يُضاعَف لمجرّد أنّ القاموسَ غيرُ فارغ.
    assert daily_load_weight(over_the_default, {"max_consecutive": 2}) == default


@pytest.mark.parametrize(
    ("cap", "factor"),
    [(4, EXPLICIT_PREFERENCE_FACTOR), (DEFAULT_MAX_DAILY, 1), (6, EXPLICIT_PREFERENCE_FACTOR)],
)
def test_solver_evaluator_and_v1_share_one_factor(cap, factor):
    """الحلّالُ ومقيِّمُه المستقلّ والمُقيِّمُ القديم: لكلّ سقفٍ عاملٌ واحد، فتتّفق درجةُ الجودة."""
    over = len(TIMES) - cap
    expected = factor * over * (over + 1) // 2

    assert _solver_units(_pref(cap)) == _evaluator_units(_pref(cap)) == expected
    # القديمُ يقيس عند كلّ وضع: الحصّةُ التي تبلغ السقفَ تجاوزٌ واحدٌ بوزنٍ واحد ← يبقى العاملُ وحدَه.
    assert daily_load_weight(cap, {"max_daily": cap}, weight=1) == factor
