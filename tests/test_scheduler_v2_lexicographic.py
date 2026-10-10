"""الهدف المعجميّ المتتالي وفجوة المتعذّرات في V2 (W-20261003-017، V2-S4).

ثلاثةُ أمور: (1) الفجوةُ خلف خيارٍ افتراضُه الصرامة (نموذجٌ مطابقٌ بنيةً وحلّاً)، (2) الطبقاتُ لا تُضحّى عليا
بدنيا، (3) إعادةُ الإنتاج: تشغيلان حقيقيّان بالبذرة والعمّال المثبَّتين.
"""

from types import SimpleNamespace

import pytest

pytest.importorskip("ortools")
from ortools.sat.python import cp_model  # noqa: E402

from operations.scheduler_v2 import runner  # noqa: E402
from operations.scheduler_v2.model import ModelOptions, build_model, unplaced_total  # noqa: E402
from operations.scheduler_v2.objective import build_objective  # noqa: E402
from tests.test_scheduler_v2_hard import make  # noqa: E402

ALL_DAYS_OFF = frozenset(("T1", d) for d in range(5))


def _opts(**kw):
    kw.setdefault("derived_day_cap", False)
    return ModelOptions(**kw)


def test_the_default_model_is_unchanged_without_the_gap_option():
    """الافتراض (allow_unplaced=False) يعطي النموذجَ نفسه بلا فجوة: بنيةً (proto) وحلّاً."""
    rows = [("C1", "S1", "T1", "", 3), ("C2", "S2", "T2", "", 2)]
    plain = build_model(make(rows), _opts())
    explicit = build_model(make(rows), _opts(allow_unplaced=False))
    assert str(plain.model.Proto()) == str(explicit.model.Proto())
    assert not any(k[0] == "unplaced" for k in plain.vars)
    assert plain.constraint_counts["DEMAND"] == 2 and "DEMAND_SLACK" not in plain.constraint_counts
    assert unplaced_total(plain) == 0

    gapped = build_model(make(rows), _opts(allow_unplaced=True))
    assert (
        gapped.constraint_counts["DEMAND_SLACK"] == 2 and "DEMAND" not in gapped.constraint_counts
    )
    for built in (plain, gapped):
        solver = cp_model.CpSolver()
        solver.parameters.random_seed = 7
        assert solver.Solve(built.model) in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    # وحين لا حاجة للفجوة تُغلَق على صفرٍ بالتصغير: لا حصّةَ تضيع بلا سبب
    gapped.model.Minimize(unplaced_total(gapped))
    solver = cp_model.CpSolver()
    assert solver.Solve(gapped.model) == cp_model.OPTIMAL and solver.ObjectiveValue() == 0


def test_an_unplaceable_demand_is_infeasible_by_default_and_a_counted_gap_with_the_option():
    rows = [("C1", "S1", "T1", "", 3)]
    strict = build_model(make(rows, ex_full=ALL_DAYS_OFF), _opts())
    solver = cp_model.CpSolver()
    assert solver.Solve(strict.model) == cp_model.INFEASIBLE

    gapped = build_model(make(rows, ex_full=ALL_DAYS_OFF), _opts(allow_unplaced=True))
    gapped.model.Minimize(unplaced_total(gapped))
    solver = cp_model.CpSolver()
    assert solver.Solve(gapped.model) == cp_model.OPTIMAL
    assert solver.ObjectiveValue() == 3  # المتعذّرُ معدودٌ لا استحالة


def _layered(case):
    """نموذجٌ صغير: التضحيةُ بالأعلى تُربح الأدنى كثيراً — لو جُمعت الطبقاتُ موزونةً لاختيرت."""
    model = cp_model.CpModel()
    u = model.NewIntVar(0, 1, "u")
    v = model.NewIntVar(0, 5, "v")
    q = model.NewIntVar(0, 100, "q")
    model.Add(q == 100 - 99 * u)  # u=1 ← الدرجة 1 بدل 100
    model.Add(v == 3 - 3 * u)
    layers = {"unplaced": u, "violations": v, "quality": q}
    built = SimpleNamespace(model=model, x={}, vars={}, inputs=SimpleNamespace(demand=[]))
    built.layers = [(name, layers[name]) for name in case]
    return built


def test_lexicographic_never_trades_a_higher_layer_for_a_lower_one():
    config = runner.SolverConfig(seed=3, workers=1, max_seconds=20)
    lex = runner.solve(_layered(["unplaced", "violations", "quality"]), config)
    assert lex.status == "OPTIMAL"
    assert lex.layers == {"unplaced": 0, "violations": 3, "quality": 100}
    assert lex.unplaced == 0
    # الهدف الموزون الواحد (بلا طبقات) كان يضحّي بالمتعذّر: يختار u=1 لأنّ مجموعه أصغر
    single = _layered(["unplaced", "violations", "quality"])
    single.model.Minimize(single.layers[0][1] + single.layers[1][1] + single.layers[2][1])
    single.layers = []
    flat = runner.solve(single, config)
    assert flat.objective == 2.0  # u=1 فمجموعه 1+0+1 أصغر من 0+3+100: ضحّى بالمتعذّر


def test_lexicographic_off_or_a_single_layer_solves_as_before():
    config = runner.SolverConfig(seed=3, workers=1, max_seconds=20, lexicographic=False)
    built = _layered(["unplaced", "violations", "quality"])
    built.model.Minimize(built.layers[2][1])
    report = runner.solve(built, config)
    assert report.layers == {} and report.objective == 1.0


def test_a_failing_first_layer_returns_its_status_without_a_slots_claim():
    built = _layered(["unplaced", "quality"])
    built.model.Add(built.layers[0][1] >= 2)  # u ∈ {0,1}: مستحيل
    report = runner.solve(built, runner.SolverConfig(seed=1, workers=1, max_seconds=10))
    assert report.status == "INFEASIBLE" and report.slots == [] and report.layers == {}


def test_report_exposes_layers_outside_the_evaluator_solver_keys():
    report = runner.SolveReport("OPTIMAL", "v", 1, 1, 0.1, layers={"unplaced": 0}, unplaced=0)
    assert set(report.solver_dict()) == {"status", "seed", "workers", "seconds"}
    assert report.lexicographic_dict() == {"layers": {"unplaced": 0}, "unplaced": 0}


def test_objective_layers_use_penalties_for_violations_and_the_weighted_total_for_quality():
    rows = [("C1", "S1", "T1", "", 2), ("C2", "S2", "T2", "", 2)]
    built = build_model(make(rows), _opts(allow_unplaced=True))
    objective = build_objective(built, {})
    names = [n for n, _e in objective.layers(built)]
    assert names == ["unplaced", "violations", "quality"]


def test_two_real_single_worker_runs_give_the_same_slots():
    """شرطُ التطابق المعلَن: حلّالٌ حقيقيّ بعاملٍ واحدٍ وبذرةٍ مثبَّتة ⇒ الحصصُ نفسُها حرفاً.

    ومع عدّة عمّالٍ في CP-SAT لا يُضمن التطابق (تفاعلُ الخيوط)، فلا يُدَّعى هنا ويُقاس في التقرير.
    """
    rows = [
        ("C1", "S1", "T1", "", 3),
        ("C1", "S2", "T2", "", 3),
        ("C2", "S1", "T1", "", 3),
        ("C2", "S3", "T3", "", 2),
    ]
    config = runner.SolverConfig(seed=11, workers=1, max_seconds=60)
    runs = []
    for _ in range(2):
        built = build_model(make(rows), _opts())
        objective = build_objective(built, {})
        built.model.Minimize(objective.total)
        runs.append(runner.solve(built, config))
    assert runs[0].status == runs[1].status and runs[0].status in ("OPTIMAL", "FEASIBLE")
    assert runs[0].slots == runs[1].slots and runs[0].objective == runs[1].objective


def _real(rows, **kw):
    from operations.scheduler_v2.model import add_layers, add_soft_terms

    inp = make(rows, **kw)
    built = build_model(inp, _opts(allow_unplaced=True))
    objective = build_objective(built, {})
    add_soft_terms(built, objective.as_terms())
    add_layers(built, objective.layers(built))
    return built


def test_real_model_with_a_full_placement_probes_zero_and_pins_it():
    built = _real([("C1", "S1", "T1", "", 3), ("C2", "S2", "T2", "", 2)])
    config = runner.SolverConfig(seed=5, workers=1, max_seconds=60, allow_unplaced=True)
    report = runner.solve(built, config)
    assert report.status in ("OPTIMAL", "FEASIBLE")
    assert report.unplaced == 0 and report.layers["unplaced"] == 0
    assert len(report.slots) == 5  # كلُّ الحصص موضوعة


def test_real_model_with_an_impossible_row_minimises_the_gap_and_places_the_rest():
    rows = [("C1", "S1", "T1", "", 3), ("C2", "S2", "T2", "", 2)]
    built = _real(rows, ex_full=ALL_DAYS_OFF)
    config = runner.SolverConfig(seed=5, workers=1, max_seconds=60, allow_unplaced=True)
    report = runner.solve(built, config)
    assert report.status in ("OPTIMAL", "FEASIBLE")
    assert report.unplaced == 3, "حصص T1 الثلاث متعذّرة لأنّه مفرَّغٌ كلَّ الأيام"
    assert len(report.slots) == 2  # حصتا T2 وُضعتا
