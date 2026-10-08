"""اختبارات أوزان V2 ودالّة هدفه (W-20261003-016): المدى والتعداد المغلق، ومطابقةُ الترميز للمقيِّم.

الحجّةُ المركزيّة: قيمةُ هدف CP-SAT على أيّ جدولٍ مُثبَّت = كلفةُ المقيِّم المستقلّ
(`evaluate_placements`، بلا حلّال) — فتنكشف كلُّ كلفةٍ ينقصها متغيّرٌ مساعدٌ أو يزيد.
"""

import json
import random
from types import SimpleNamespace

import pytest

from operations.constraint_registry import SOFT_CONSTRAINTS
from operations.cpsat_adapter import CpSatInputs, DemandRow, TeacherPref
from operations.scheduler_v2 import soft_constraints as sc
from operations.scheduler_v2.objective import (
    BONUS_KEYS,
    DEFAULT_WEIGHTS,
    MAX_WEIGHT,
    WeightError,
    build_objective,
    validate_weights,
    weighted_cost,
    weights_from_json,
)

cp_model = pytest.importorskip("ortools.sat.python.cp_model")

# ── الأوزان ────────────────────────────────────────────────────────────────


def test_default_weights_are_the_registry_and_keys_are_closed():
    assert set(DEFAULT_WEIGHTS) == set(sc.SOFT_KEYS) == {s.code for s in SOFT_CONSTRAINTS}
    assert len(DEFAULT_WEIGHTS) == 13
    assert all(isinstance(w, int) for w in DEFAULT_WEIGHTS.values())
    assert BONUS_KEYS == {"double_bonus", "first_period_floor"}
    # كلُّ مفتاحٍ له مُنشئُ تعبير — لا قيدَ بلا ترميز
    assert set(sc.BUILDERS) == set(sc.SOFT_KEYS)


def test_defaults_sit_inside_their_own_range():
    assert validate_weights(None) == DEFAULT_WEIGHTS
    assert max(abs(w) for w in DEFAULT_WEIGHTS.values()) < MAX_WEIGHT


def test_override_changes_only_named_key_and_does_not_mutate_input():
    raw = {"gap": 20}
    out = validate_weights(raw)
    assert out["gap"] == 20
    assert {k: v for k, v in out.items() if k != "gap"} == {
        k: v for k, v in DEFAULT_WEIGHTS.items() if k != "gap"
    }
    assert raw == {"gap": 20}


@pytest.mark.parametrize(
    "raw",
    [
        {"nonexistent": 1},  # مفتاحٌ خارج التعداد
        {"gap": 101},  # فوق المدى
        {"gap": -1},  # عقوبةٌ بإشارة مكافأة
        {"double_bonus": 1},  # مكافأةٌ بإشارة عقوبة
        {"first_period_floor": -101},
        {"gap": 1.5},  # ليس صحيحاً
        {"gap": "8"},  # نصّ
        {"gap": True},  # bool ليس وزناً
        {"gap": None},
    ],
)
def test_invalid_weights_rejected(raw):
    with pytest.raises(WeightError):
        validate_weights(raw)


def test_range_edges_are_inclusive_and_zero_allowed():
    out = validate_weights({"gap": 0, "core_early": MAX_WEIGHT, "double_bonus": -MAX_WEIGHT})
    assert (out["gap"], out["core_early"], out["double_bonus"]) == (0, MAX_WEIGHT, -MAX_WEIGHT)


def test_json_loader_is_plain_json_only():
    assert weights_from_json('{"gap": 9}')["gap"] == 9
    for bad in ("[1]", "3", '{"gap": 1e3}', '{"gap": 9, "x": 1}'):
        with pytest.raises((WeightError, ValueError)):
            weights_from_json(bad)
    with pytest.raises(ValueError):  # ليست JSON — لا eval
        weights_from_json("{'gap': __import__('os')}")


# ── نموذجٌ صغيرٌ يحوي كلَّ القيود ──────────────────────────────────────────────

REGULAR_TIMES = {
    1: (430, 480),
    2: (480, 530),
    3: (530, 575),
    4: (600, 650),
    5: (650, 695),
    6: (695, 740),
    7: (760, 810),
}
THURSDAY_TIMES = {p: t for p, t in REGULAR_TIMES.items() if p <= 6}

PEDAGOGY = {"HV": "heavy", "AC": "activity", "DB": "regular", "RG": "regular", "HI": "regular"}


def _inputs() -> CpSatInputs:
    inputs = CpSatInputs()
    inputs.class_band = {"C1": "B", "C2": "B"}
    inputs.class_level = {"C1": "prep", "C2": "prep"}
    inputs.bell = {
        "B|regular": {"periods": list(REGULAR_TIMES), "touch": [(1, 2), (2, 3), (4, 5), (5, 6)]},
        "B|thursday": {"periods": list(THURSDAY_TIMES), "touch": [(1, 2), (2, 3), (4, 5), (5, 6)]},
    }
    inputs.times = {"B|regular": REGULAR_TIMES, "B|thursday": THURSDAY_TIMES}
    inputs.doubles = frozenset({"DB"})
    inputs.demand = [
        DemandRow("C1", "HV", "T1", "", 5),
        DemandRow("C1", "AC", "T2", "", 2),
        DemandRow("C1", "DB", "T3", "", 2),
        DemandRow("C1", "RG", "T1", "", 3),
        DemandRow("C2", "HV", "T1", "", 4),
        DemandRow("C2", "AC", "T2", "", 2),
        DemandRow("C2", "HI", "T3", "", 5),
        DemandRow("C2", "RG", "T2", "", 3),
    ]
    inputs.prefs = {
        "T1": TeacherPref("T1", 2, None, None, 0),  # سقفٌ يوميٌّ 2 ويومُ تفريغٍ مطلوب
        "T3": TeacherPref("T3", None, None, None, 3),
    }
    return inputs


def _built(inputs=None):
    inputs = inputs or _inputs()
    model = cp_model.CpModel()
    x = {}
    for i, row in enumerate(inputs.demand):
        for d in range(5):
            for p in inputs.periods(row.cls, d):
                x[i, d, p] = model.NewBoolVar(f"x{i}_{d}_{p}")
    for i, row in enumerate(inputs.demand):
        model.Add(sum(v for k, v in x.items() if k[0] == i) == row.n)
    for key in {(r.cls, d, p) for (i, d, p) in x for r in [inputs.demand[i]]}:
        model.Add(sum(v for (i, d, p), v in x.items() if (inputs.demand[i].cls, d, p) == key) <= 1)
    for key in {(inputs.demand[i].teacher, d, p) for (i, d, p) in x}:
        model.Add(
            sum(v for (i, d, p), v in x.items() if (inputs.demand[i].teacher, d, p) == key) <= 1
        )
    return SimpleNamespace(model=model, x=x, inputs=inputs)


def _solve(built, seed=0, seconds=30):
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = seed
    status = solver.Solve(built.model)
    return solver, status


def _random_schedule(seed, prefer_double=False):
    """جدولٌ مقبولٌ (قيودُ الجدوى الأساسيّةُ فقط) متنوّعٌ بالبذرة: يُصغَّر فيه مزيجٌ عشوائيٌّ.

    `prefer_double` يدفع المادّةَ المزدوجةَ إلى حصّتين متجاورتين صباحَ الأحد (يغطّي double_bonus).
    """
    rng = random.Random(seed)
    built = _built()
    bonus = {
        key: -50
        if prefer_double
        and built.inputs.demand[key[0]].subj == "DB"
        and key[1] == 0
        and key[2] in (1, 2)
        else 0
        for key in built.x
    }
    built.model.Minimize(sum((rng.randint(-5, 5) + bonus[k]) * v for k, v in built.x.items()))
    solver, status = _solve(built, seed, seconds=2)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    return {k for k, v in built.x.items() if solver.Value(v)}


def _random_weights(rng):
    return {
        k: rng.randint(-MAX_WEIGHT // 4, 0) if k in BONUS_KEYS else rng.randint(0, MAX_WEIGHT // 4)
        for k in DEFAULT_WEIGHTS
    }


def _cost_in_solver(placements, weights):
    """هدفُ CP-SAT على جدولٍ مُثبَّت: المتغيّراتُ المساعدةُ وحدَها تُترك للحلّال."""
    built = _built()
    for key, var in built.x.items():
        built.model.Add(var == (1 if key in placements else 0))
    obj = build_objective(built, PEDAGOGY, weights)
    obj.apply(built.model)
    solver, status = _solve(built, seconds=10)
    assert status == cp_model.OPTIMAL, solver.StatusName(status)
    return built, solver, obj


def test_objective_value_equals_independent_evaluator_on_fixed_schedules():
    """الحجّةُ المركزيّة: لكلّ جدولٍ مُثبَّتٍ ووزنٍ — هدفُ CP-SAT = كلفةُ المقيِّم، وتفصيلُه قيداً قيداً."""
    for seed in range(6):
        placements = _random_schedule(seed)
        weights = _random_weights(random.Random(1000 + seed))
        built, solver, obj = _cost_in_solver(placements, weights)
        units = sc.evaluate_placements(built.inputs, PEDAGOGY, placements, built.x.keys())
        assert obj.breakdown(solver) == units, seed
        assert round(solver.ObjectiveValue()) == weighted_cost(units, weights), seed


def test_every_soft_constraint_is_exercised_by_the_fixture():
    """لو كان قيدٌ صفراً في كلّ الجداول فاختبارُ المطابقة أعلاه لا يحرسه."""
    seen = dict.fromkeys(sc.SOFT_KEYS, 0)
    for seed in range(12):
        built = _built()
        units = sc.evaluate_placements(
            built.inputs,
            PEDAGOGY,
            _random_schedule(seed, prefer_double=seed % 3 == 0),
            built.x.keys(),
        )
        for k, v in units.items():
            seen[k] += v
    zero = [k for k, v in seen.items() if v == 0]
    assert not zero, f"قيودٌ لا تظهر في أيّ جدولٍ مجرَّب فلا يحرسها الاختبار: {zero}"


def test_minimizing_weighted_objective_never_beats_evaluator_lower_bound():
    """عند التصغير الحرّ (مهلةٌ قصيرة) لا يهبط الهدفُ المُبلَّغ تحت كلفة جدوله الحقيقيّة."""
    weights = _random_weights(random.Random(7))
    built = _built()
    build_objective(built, PEDAGOGY, weights).apply(built.model)
    solver, status = _solve(built, seconds=3)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    units = sc.evaluate_placements(
        built.inputs, PEDAGOGY, {k for k, v in built.x.items() if solver.Value(v)}, built.x.keys()
    )
    assert solver.ObjectiveValue() >= weighted_cost(units, weights) - 1e-6


def test_no_movement_term_and_no_existing_schedule_input():
    """الهدفُ من الصفر: لا حدَّ يقيس الحركةَ ولا مدخلَ يحمل جدولاً قائماً."""
    import inspect

    from operations.scheduler_v2 import objective

    src = inspect.getsource(objective) + inspect.getsource(sc)
    assert "current" not in inspect.signature(objective.build_objective).parameters
    assert "cur_cells" not in src and "kept" not in src


def test_objective_does_not_minimize_by_itself():
    built = _built()
    obj = build_objective(built, PEDAGOGY)
    assert not built.model.HasObjective()
    obj.apply(built.model)
    assert built.model.HasObjective()
    assert set(obj.terms) == set(sc.SOFT_KEYS)
    assert json.dumps(obj.weights)  # أعدادٌ صحيحةٌ تُسلسَل


def test_as_terms_matches_add_soft_terms_contract():
    obj = build_objective(_built(), PEDAGOGY, {"gap": 3})
    terms = obj.as_terms()
    assert [k for k, _e, _w in terms] == list(sc.SOFT_KEYS)
    assert {k: w for k, _e, w in terms}["gap"] == 3
