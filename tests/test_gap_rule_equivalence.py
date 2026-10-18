"""[SCHEDULE-V2] تعريفٌ واحدٌ لسقف الفراغ في الحلّال والمُقيِّم (W-20261012-023).

الحلّال كان يعدّ **مجموع** الفراغات والمُقيِّمُ **أوسعَ** فراغٍ مفرد. فهنا تُجرَّب كلُّ أنماط الإشغال لـn ≤ 8 ×
كلُّ سقفٍ من 0 إلى 5: الحلّالُ يقبل النمطَ ⇔ `widest_gap(النمط) ≤ السقف` ⇔ المُقيِّمُ يقبله بالقارئ نفسِه.
والبياناتُ مصنّعةٌ بلا أسماءٍ ولا هويّات (PDPPL، D-381م).
"""

from itertools import product
from types import SimpleNamespace

import pytest
from ortools.sat.python import cp_model

from operations.gap_rule import effective_max_gap, widest_gap, widest_gap_of_positions
from operations.scheduler_v2.hard_constraints import _gap_within
from operations.scheduling_inputs import ScheduleGrid

CAPS = range(0, 6)
SIZES = range(2, 9)


def _solver_accepts(flags: tuple[bool, ...], cap: int) -> bool:
    model = cp_model.CpModel()
    keys = [(i, i + 1) for i in range(len(flags))]
    occ = {}
    for key, flag in zip(keys, flags, strict=True):
        var = model.NewBoolVar("")
        model.Add(var == int(flag))
        occ[key] = var
    _gap_within(SimpleNamespace(m=model, count=lambda _code: None), keys, occ, cap)
    solver = cp_model.CpSolver()
    return solver.Solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE)


def _evaluator_widest(flags: tuple[bool, ...]) -> int:
    grid = ScheduleGrid()
    grid._teacher_slots["t"] = [(0, i + 1) for i, flag in enumerate(flags) if flag]
    return grid.teacher_widest_gap_with("t", 0, [])


def test_widest_gap_is_the_single_widest_empty_run_between_occupied_slots():
    assert widest_gap([False, True, False, False, True, False, True, False]) == 2
    assert widest_gap([True, False, True, False, True]) == 1  # مجموعُها 2 وأوسعُها 1
    assert widest_gap([False, False, True]) == 0  # ما قبل الأوّل وبعد الأخير ليس فراغاً
    assert widest_gap([True]) == 0
    assert widest_gap([]) == 0


@pytest.mark.parametrize("n", SIZES)
def test_the_solver_and_the_evaluator_agree_on_every_pattern_and_every_cap(n):
    for flags in product((False, True), repeat=n):
        widest = widest_gap(flags)
        assert _evaluator_widest(flags) == widest
        for cap in CAPS:
            assert _solver_accepts(flags, cap) == (widest <= cap), (flags, cap)


def test_the_evaluator_counts_positions_like_the_flags():
    assert widest_gap_of_positions([1, 4, 5]) == 2
    assert widest_gap_of_positions([3]) == 0
    assert widest_gap_of_positions([]) == 0


def test_a_stored_gap_cap_is_ignored_while_the_flag_is_off(settings):
    settings.PREF_MAX_GAP_ACTIVE = False
    assert effective_max_gap(1) is None
    assert effective_max_gap(0) is None
    assert effective_max_gap(None) is None


def test_a_stored_gap_cap_applies_while_the_flag_is_on(settings):
    settings.PREF_MAX_GAP_ACTIVE = True
    assert effective_max_gap(1) == 1
    assert effective_max_gap(0) == 0  # الصفرُ قيدٌ صحيح: لا فراغَ البتّة
    assert effective_max_gap(None) is None
