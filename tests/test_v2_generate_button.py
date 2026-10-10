"""[SCHEDULE] زرُّ «ولّد» يولّد من V2 (W-20261010-031): الاستدعاءُ والإشعارُ والمؤشّراتُ والسقوفُ وحالةُ الصفحة."""

from datetime import timedelta
from pathlib import Path

import pytest
from django.urls import reverse
from django.utils import timezone

from operations.models import ScheduleGeneration
from operations.scheduler_v2 import runner
from operations.scheduler_v2.limits import (
    GENERATION_SOFT_TIME_LIMIT,
    GENERATION_STALE_AFTER_SECONDS,
    SOLVER_MAX_SECONDS,
)
from operations.scheduler_v2.tasks import generate_schedule_v2_task
from operations.tasks import reap_stuck_schedule_generations_task

YEAR = "2026-2027"


def _queued(school, **extra):
    return ScheduleGeneration.objects.create(
        school=school, academic_year=YEAR, status="queued", **extra
    )


def _spy_side_effects(monkeypatch):
    notified, measured = [], []
    monkeypatch.setattr(
        "operations.tasks._notify_generation_done",
        lambda g, *, ok, summary: notified.append((ok, summary)),
    )
    monkeypatch.setattr("operations.schedule_lab.store_metrics", lambda g: measured.append(g.pk))
    return notified, measured


def _fake_success(slots=7):
    def run_generation(generation, config, **kwargs):
        ScheduleGeneration.objects.filter(pk=generation.pk).update(
            status="draft",
            total_slots_created=slots,
            soft_violations=3,
            config_snapshot={"engine": runner.ENGINE},
        )
        return runner.RunResult(True, None, None, "", "ok")

    return run_generation


@pytest.mark.django_db
def test_success_stores_lab_metrics_and_notifies(school, monkeypatch):
    notified, measured = _spy_side_effects(monkeypatch)
    monkeypatch.setattr(runner, "run_generation", _fake_success())
    gen = _queued(school)

    outcome = generate_schedule_v2_task.run(str(gen.pk))

    assert outcome == {"ok": True, "reason": "ok"}
    assert measured == [gen.pk]
    assert len(notified) == 1 and notified[0][0] is True
    assert "7" in notified[0][1]


@pytest.mark.django_db
def test_a_metrics_failure_does_not_fail_a_good_generation(school, monkeypatch):
    notified, _ = _spy_side_effects(monkeypatch)

    def boom(generation):
        raise RuntimeError("metrics")

    monkeypatch.setattr("operations.schedule_lab.store_metrics", boom)
    monkeypatch.setattr(runner, "run_generation", _fake_success())
    gen = _queued(school)

    outcome = generate_schedule_v2_task.run(str(gen.pk))

    gen.refresh_from_db()
    assert outcome["ok"] is True and gen.status == "draft"
    assert notified and notified[0][0] is True


@pytest.mark.django_db
def test_a_rejected_run_marks_failed_and_notifies(school, monkeypatch):
    notified, measured = _spy_side_effects(monkeypatch)

    def rejected(generation, config, **kwargs):
        result = runner.RunResult(False, None, None, "رفضه المُقيِّم", "rejected")
        runner.fail_generation(generation, result)
        return result

    monkeypatch.setattr(runner, "run_generation", rejected)
    gen = _queued(school)

    outcome = generate_schedule_v2_task.run(str(gen.pk))

    gen.refresh_from_db()
    assert outcome["ok"] is False
    assert gen.status == "failed" and gen.error_message == "رفضه المُقيِّم"
    assert measured == [] and notified == [(False, "رفضه المُقيِّم")]


@pytest.mark.django_db
def test_an_exception_marks_failed_not_running_and_notifies(school, monkeypatch):
    notified, _ = _spy_side_effects(monkeypatch)

    def explode(generation, config, **kwargs):
        raise RuntimeError("solver crashed")

    monkeypatch.setattr(runner, "run_generation", explode)
    gen = _queued(school)

    outcome = generate_schedule_v2_task.run(str(gen.pk))

    gen.refresh_from_db()
    assert outcome == {"ok": False, "reason": "exception"}
    assert gen.status == "failed" and gen.error_message
    assert notified and notified[0][0] is False


@pytest.mark.django_db
def test_an_early_stop_keeps_the_best_draft_without_failure(school, monkeypatch):
    notified, measured = _spy_side_effects(monkeypatch)
    monkeypatch.setattr(runner, "run_generation", _fake_success(slots=5))
    gen = _queued(school)

    generate_schedule_v2_task.run(str(gen.pk))

    gen.refresh_from_db()
    assert gen.status == "draft" and gen.total_slots_created == 5
    assert measured and notified[0][0] is True


def test_every_ceiling_comes_from_one_source():
    assert SOLVER_MAX_SECONDS == runner.DEFAULT_MAX_SECONDS
    assert GENERATION_SOFT_TIME_LIMIT > SOLVER_MAX_SECONDS
    assert GENERATION_STALE_AFTER_SECONDS > GENERATION_SOFT_TIME_LIMIT
    assert generate_schedule_v2_task.soft_time_limit == GENERATION_SOFT_TIME_LIMIT
    from operations.views_schedule import _GENERATION_STALE_AFTER

    assert _GENERATION_STALE_AFTER.total_seconds() == GENERATION_STALE_AFTER_SECONDS


@pytest.mark.django_db
def test_a_long_valid_run_is_not_reaped_nor_unblocked(school):
    from operations.views_schedule import _reap_stale_generations

    running = _queued(school)
    ScheduleGeneration.objects.filter(pk=running.pk).update(
        status="running", generated_at=timezone.now() - timedelta(minutes=25)
    )

    assert reap_stuck_schedule_generations_task.run() == {"reaped": 0}
    assert _reap_stale_generations(school, YEAR) is not None
    running.refresh_from_db()
    assert running.status == "running"


def test_the_button_no_longer_queues_the_v1_task():
    source = Path("operations/views_schedule.py").read_text(encoding="utf-8")
    assert "generate_smart_schedule_task" not in source
    assert "generate_schedule_v2_task.delay(str(generation.id))" in source


@pytest.mark.django_db
def test_status_of_a_v2_row_hides_the_misleading_zero_quality(client_as, principal_user, school):
    gen = _queued(school)
    ScheduleGeneration.objects.filter(pk=gen.pk).update(
        status="draft",
        total_slots_created=40,
        soft_violations=9,
        config_snapshot={"engine": runner.ENGINE},
    )

    response = client_as(principal_user).get(reverse("smart_generate_status"), {"year": YEAR})

    data = response.json()
    assert data["quality"] is None
    assert data["slots"] == 40 and data["soft_violations"] == 9
