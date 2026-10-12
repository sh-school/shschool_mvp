"""[SCHEDULE] حالاتُ الإيقاف والمهلة في توليد V2 ولقطةُ التقدّم بعد التوليد (W-20261011-010).

خللان ظهرا في قياس 10-11 على نسخة الإنتاج المزروعة: إيقافٌ يدويٌّ قبل أول حلٍّ كُتبت رسالتُه «انقضت المهلة (UNKNOWN)»
والمهلةُ لم تنقضِ؛ وحالةُ «أُوقف» تضيع من `metrics` بعد التوليد لأنّ حفظ مؤشرات المختبر كان يستبدلها كلَّها.
"""

from types import SimpleNamespace

import pytest

from operations.models import ScheduleGeneration
from operations.schedule_lab import ScheduleLab, store_metrics
from operations.scheduler_v2 import progress, runner
from tests.test_scheduler_v2_diagnosis import YEAR, _inputs

pytestmark = pytest.mark.django_db

CONFIG = runner.SolverConfig(seed=11, workers=2, max_seconds=5)


@pytest.fixture(autouse=True)
def _no_real_objective(monkeypatch):
    monkeypatch.setattr(runner, "default_objective", lambda: None)


def _empty_solve(**extra):
    """حلٌّ مُحقَن يرجع UNKNOWN بلا أي جدول — كما ينتهي حلّالٌ لم يجد شيئاً."""
    built = type("Built", (), {"model": None, "inputs": None, "x": {}})()
    return {
        "inputs": _inputs(),
        "builder": lambda inputs: built,
        "solver": lambda built, config: runner.SolveReport("UNKNOWN", "", 1, 1, 0.0),
        "objective": lambda built, inputs: None,
        **extra,
    }


def test_a_manual_stop_before_any_solution_is_not_called_a_timeout(school):
    result, _ = runner.run(
        school, YEAR, CONFIG, **_empty_solve(progress=SimpleNamespace(stop_flag=True))
    )

    assert not result.ok and result.reason == "stopped"
    assert "أوقفه المستخدم" in result.message
    assert "انقضت المهلة" not in result.message
    assert runner._final_state(result, True) == "stopped"


def test_a_real_timeout_keeps_its_own_message(school):
    result, _ = runner.run(
        school, YEAR, CONFIG, **_empty_solve(progress=SimpleNamespace(stop_flag=False))
    )

    assert result.reason == "timeout"
    assert result.message.startswith("انقضت المهلةُ (5ث) بلا حلٍّ (UNKNOWN)")
    assert "أوقفه المستخدم" not in result.message
    assert runner._final_state(result, False) == "timeout"


def test_the_stopped_empty_run_publishes_the_stopped_state_with_an_honest_label(school):
    generation = ScheduleGeneration.objects.create(
        school=school, academic_year=YEAR, status="running"
    )
    tracker = progress.ProgressTracker(generation.pk, 5)
    tracker.stop_flag = True

    result = runner.run_generation(generation, CONFIG, **_empty_solve(progress=tracker))

    generation.refresh_from_db()
    snap = progress.read_progress(generation)
    assert result.reason == "stopped" and generation.status == "failed"
    assert "أوقفه المستخدم" in generation.error_message
    assert snap["state"] == "stopped" and snap["done"] is True
    assert snap["state_label"] == progress.STOPPED_EMPTY_LABEL
    assert "أفضل حلّ" not in snap["state_label"], "لا وعدَ بحلٍّ لا وجودَ له"


def _lab_computing(monkeypatch, computed):
    monkeypatch.setattr(
        ScheduleLab,
        "for_generation",
        classmethod(lambda cls, gen: SimpleNamespace(compute=lambda: computed)),
    )


def test_storing_the_lab_metrics_keeps_every_key_that_was_there(school, monkeypatch):
    """السببُ المثبَت للخلل 3: `store_metrics` كانت تستبدل `metrics` كلَّها فتمحو لقطةَ التقدّم وعلَم الإيقاف."""
    generation = ScheduleGeneration.objects.create(
        school=school, academic_year=YEAR, status="draft"
    )
    old = {
        progress.KEY: {"state": "stopped", "state_label": "أُوقف مبكّراً بأفضل حلّ", "done": True},
        progress.STOP_KEY: True,
        "other_feature": {"x": 1},
    }
    ScheduleGeneration.objects.filter(pk=generation.pk).update(metrics=old)
    generation.refresh_from_db()
    _lab_computing(monkeypatch, {"lab_a": {"value": 3}})

    computed = store_metrics(generation)

    generation.refresh_from_db()
    assert computed == {"lab_a": {"value": 3}}
    assert generation.metrics == {**old, "lab_a": {"value": 3}}


def test_storing_the_lab_metrics_keeps_a_key_written_after_the_instance_was_loaded(
    school, monkeypatch
):
    """الخيطُ الناشرُ يكتب في الصفّ مباشرةً: ما كُتب بعد تحميل الكائن يبقى، والمحسوبُ يعلو القديمَ في المفتاح نفسِه."""
    generation = ScheduleGeneration.objects.create(
        school=school, academic_year=YEAR, status="draft"
    )
    ScheduleGeneration.objects.filter(pk=generation.pk).update(
        metrics={progress.STOP_KEY: True, "lab_a": {"value": 1}}
    )
    _lab_computing(monkeypatch, {"lab_a": {"value": 2}})

    store_metrics(generation)  # الكائنُ هنا لم يحمّل metrics الجديدة

    generation.refresh_from_db()
    assert generation.metrics[progress.STOP_KEY] is True
    assert generation.metrics["lab_a"] == {"value": 2}
