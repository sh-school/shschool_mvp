"""[SCHEDULE] سقفُ طبقة المخالفات بعد أوّل حلٍّ لها (W-20261011-010، قرار المالك D-392م).

«5 دقائق بعد أوّل حلّ، والباقي للجودة»: تتوقّف الطبقةُ غيرُ الأخيرة عند (أوّل حلّ + الثابت) أو عند حصّتها
أيّهما أسبق، ويُمنح ما وُفِّر للطبقة التالية فيبقى المجموعُ هو المهلةَ الكلّيّة. ولا سقفَ قبل أوّل حلّ.
"""

import random
import time
from types import SimpleNamespace

from ortools.sat.python import cp_model

from operations.scheduler_v2 import limits, runner


def test_the_constant_is_five_minutes_and_lives_in_the_limits_module():
    assert limits.LAYER_AFTER_FIRST_SOLUTION_SECONDS == 300
    assert runner.SolverConfig().layer_grace_seconds == 300


def _hard_cover_model(layer_two=False):
    """تغطيةٌ عشوائيّةٌ كبيرة: أوّلُ حلٍّ فوريّ وإثباتُ الأمثليّة يطول — فلا تنتهي الطبقةُ الأولى من تلقاء نفسها."""
    rng = random.Random(7)
    model = cp_model.CpModel()
    picks = [model.NewBoolVar(f"s{i}") for i in range(3000)]
    for _ in range(9000):
        model.AddBoolOr([picks[i] for i in rng.sample(range(3000), 4)])
    first = sum(picks)
    model.Minimize(first)
    built = SimpleNamespace(model=model, x={}, layers=[("violations", first)])
    if layer_two:
        built.layers.append(("quality", sum(picks[:1500]) - sum(picks[1500:])))
    return built


def test_a_non_last_layer_stops_one_grace_after_its_first_solution():
    config = runner.SolverConfig(seed=3, workers=1, max_seconds=60, layer_grace_seconds=1)

    started = time.monotonic()
    solver, code, _secs = runner._run_stage(
        _hard_cover_model(), config, None, 60, False, config.layer_grace_seconds
    )
    elapsed = time.monotonic() - started

    assert runner._status_name(cp_model, code) == "FEASIBLE", "قُطع قبل إثبات الأمثليّة ويبقى أفضلُ حلٍّ"
    assert elapsed < 20, f"لم يُقطع بعد الثانية الأولى من أوّل حلّ ({elapsed:.1f}ث)"


def test_without_a_grace_the_stage_runs_to_its_own_limit():
    config = runner.SolverConfig(seed=3, workers=1, max_seconds=4)

    started = time.monotonic()
    _solver, code, _secs = runner._run_stage(_hard_cover_model(), config, None, 4, False, None)

    assert runner._status_name(cp_model, code) == "FEASIBLE"
    assert time.monotonic() - started >= 3.5, "بلا سقفٍ تستهلك الطبقةُ حصّتَها كاملةً"


def test_the_saved_time_goes_to_the_next_layer(monkeypatch):
    """الطبقةُ الأولى تقطعها المهلةُ بعد أوّل حلّ، فتأخذ الثانيةُ كلَّ ما بقي من المهلة الكلّيّة لا نصفَها."""
    calls = []
    clock = [0.0]
    monkeypatch.setattr(runner, "time", SimpleNamespace(monotonic=lambda: clock[0]))

    def fake_run_stage(
        built, config, progress, max_seconds, report_progress, stop_after_first=None
    ):
        calls.append((round(max_seconds, 1), report_progress, stop_after_first))
        clock[0] += (
            400.0 if len(calls) == 1 else 100.0
        )  # الأولى استُهلكت 400 من 900 (قُطعت بعد أوّل حلّها)
        value = SimpleNamespace(
            Value=lambda expr: 3, ObjectiveValue=lambda: 3.0, BestObjectiveBound=lambda: 0.0
        )
        return value, cp_model.FEASIBLE, 0.0

    monkeypatch.setattr(runner, "_run_stage", fake_run_stage)
    built = SimpleNamespace(
        model=SimpleNamespace(
            ClearObjective=lambda: None,
            Minimize=lambda expr: None,
            ClearHints=lambda: None,
            AddHint=lambda var, value: None,
            Add=lambda constraint: None,
        ),
        x={},
        layers=[("violations", 1.0), ("quality", 2.0)],
    )
    config = runner.SolverConfig(seed=1, workers=1, max_seconds=1800)

    runner._solve_layers(built, config, None, built.layers)

    assert calls[0] == (900.0, False, 300), "الأولى: حصّتُها وسقفُها بعد أوّل حلّ"
    assert calls[1] == (1400.0, True, None), "الثانية: كلُّ ما بقي (1800-400) بلا سقف"


def test_only_the_violations_layer_is_capped_never_unplaced(monkeypatch):
    """قرار المالك سمّى طبقة المخالفات وحدَها: طبقةُ المتعذّرات (إن فُعّلت وفشل الجسّ) لا تُقطع بعد أوّل حلّ."""
    graces = {}
    names = iter(["unplaced", "violations", "quality"])

    def fake_run_stage(
        built, config, progress, max_seconds, report_progress, stop_after_first=None
    ):
        graces[next(names)] = stop_after_first
        value = SimpleNamespace(
            Value=lambda expr: 3, ObjectiveValue=lambda: 3.0, BestObjectiveBound=lambda: 0.0
        )
        return value, cp_model.FEASIBLE, 0.0

    monkeypatch.setattr(runner, "_run_stage", fake_run_stage)
    monkeypatch.setattr(runner, "_probe_full_placement", lambda *args: None)
    built = SimpleNamespace(
        model=SimpleNamespace(
            ClearObjective=lambda: None,
            Minimize=lambda expr: None,
            ClearHints=lambda: None,
            AddHint=lambda var, value: None,
            Add=lambda constraint: None,
        ),
        x={},
        layers=[("unplaced", 1.0), ("violations", 2.0), ("quality", 3.0)],
    )
    config = runner.SolverConfig(seed=1, workers=1, max_seconds=1800)

    runner._solve_layers(built, config, None, built.layers)

    assert graces == {"unplaced": None, "violations": 300, "quality": None}
