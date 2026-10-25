"""[SCHEDULE] التشغيلُ الظلّيّ لـV2 (W-20261003-018، قرار المالك D-318م، الخطُّ الأحمر D-381م).

يشغّل V2 وحدَه على مدخلات المدرسة ويقارنه بالمعتمَد ويقيس الزمن، بلا أثرٍ على الجدول الحيّ ولا على التوليد.
الحلّالُ يُحقن مزيَّفاً (كما في اختبارات المشغّل) فيُختبر المسارُ نفسُه: الحدّان، وعدمُ الكتابة في المعتمَد، والإذن.
"""

import json
from datetime import time

import pytest

from operations.models import ScheduleGeneration, ScheduleSlot
from operations.scheduler_v2 import runner, tasks
from tests.test_scheduler_v2_runner import (  # noqa: F401 — مجهّزاتُ المشهد نفسُها
    CONFIG,
    YEAR,
    _fake,
    _no_real_objective,
    known_good,
    scene,
)

pytestmark = pytest.mark.django_db


def _approved_live(school, rows):
    """جدولٌ حيٌّ معتمَدٌ بالصفوف نفسِها — هو ما يجب ألّا يتغيّر منه شيء."""
    live = ScheduleGeneration.objects.create(school=school, academic_year=YEAR, status="approved")
    ScheduleSlot.objects.bulk_create(
        [
            ScheduleSlot(
                school=school,
                teacher_id=teacher,
                class_group_id=cls,
                subject_id=subj,
                day_of_week=day,
                period_number=period,
                start_time=time(6 + period, 0),
                end_time=time(6 + period, 45),
                academic_year=YEAR,
                is_active=True,
                generation=live,
            )
            for cls, subj, teacher, day, period in rows
        ]
    )
    return live


@pytest.fixture(autouse=True)
def _tmp_default_storage(settings, tmp_path):
    settings.STORAGES = {
        **settings.STORAGES,
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(tmp_path)},
        },
    }


def _live_snapshot(school):
    return sorted(
        ScheduleSlot.objects.filter(school=school, is_active=True).values_list(
            "id", "teacher_id", "class_group_id", "subject_id", "day_of_week", "period_number"
        )
    )


def test_shadow_run_compares_with_the_approved_schedule_and_leaves_it_untouched(known_good):
    school, rows = known_good
    _approved_live(school, rows)
    before = _live_snapshot(school)
    builder, solver, _ = _fake("OPTIMAL", rows)

    outcome = tasks.run_shadow(school, YEAR, CONFIG, builder=builder, solver=solver)

    assert outcome["ok"] and outcome["state"] == "ok"
    assert _live_snapshot(school) == before, "الجدولُ الحيّ المعتمَد لم يتغيّر"
    assert not ScheduleSlot.objects.filter(is_active=False).exists(), "لا حصّةَ باقيةٌ من الظلّ"
    assert ScheduleGeneration.objects.filter(school=school).count() == 1, "لا صفَّ توليدٍ باقٍ"
    stored = tasks.read_shadow_report(school.pk, outcome["run_id"])
    assert stored["state"] == "ok" and stored["elapsed_seconds"] >= 0
    comparison = stored["comparison"]
    assert comparison["has_live"] is True
    assert {row["code"] for row in comparison["rows"]} == {
        "IND-02",
        "IND-04",
        "IND-08",
        "IND-13",
        "IND-16",
    }
    # الجدولان هنا الصفوفُ نفسُها فلا حصّةَ متغيّرة.
    assert comparison["changed_slots"] == {"added": 0, "removed": 0}


def test_shadow_record_holds_values_only_no_names(known_good):
    school, rows = known_good
    _approved_live(school, rows)
    builder, solver, _ = _fake("OPTIMAL", rows)

    outcome = tasks.run_shadow(school, YEAR, CONFIG, builder=builder, solver=solver)

    dumped = json.dumps(tasks.read_shadow_report(school.pk, outcome["run_id"]), ensure_ascii=False)
    assert "معلّم 0" not in dumped and "معلّم 1" not in dumped and "مادّة" not in dumped


def test_a_timeout_is_recorded_with_its_time_and_no_comparison(known_good):
    school, rows = known_good
    _approved_live(school, rows)
    before = _live_snapshot(school)
    builder, solver, _ = _fake("UNKNOWN")

    outcome = tasks.run_shadow(school, YEAR, CONFIG, builder=builder, solver=solver)

    assert not outcome["ok"] and outcome["state"] == "timeout"
    stored = tasks.read_shadow_report(school.pk, outcome["run_id"])
    assert stored["comparison"] is None
    assert stored["max_seconds"] == CONFIG.max_seconds and stored["state"] == "timeout"
    assert _live_snapshot(school) == before


def test_a_busy_school_is_recorded_not_raised(known_good, monkeypatch):
    school, rows = known_good

    def busy(*args, **kwargs):
        raise runner.SchoolBusyError("حلٌّ آخرُ جارٍ لهذه المدرسة")

    monkeypatch.setattr(runner, "run", busy)

    outcome = tasks.run_shadow(school, YEAR, CONFIG)

    assert not outcome["ok"] and outcome["state"] == "busy"


def test_the_task_refuses_without_the_explicit_permission(known_good, monkeypatch):
    school, _rows = known_good
    monkeypatch.delenv(tasks.SHADOW_ENV, raising=False)

    assert tasks.shadow_schedule_v2_task.run(str(school.pk)) == {
        "ok": False,
        "reason": "not_allowed",
    }
    with pytest.raises(tasks.ShadowNotAllowedError):
        tasks.request_shadow_run(school)
    assert not ScheduleGeneration.objects.filter(school=school).exists()
    assert tasks.read_shadow_report(school.pk, "x") is None


def test_a_request_is_idempotent_within_the_window(known_good, monkeypatch):
    from django.core.cache import cache

    school, _rows = known_good
    monkeypatch.setenv(tasks.SHADOW_ENV, "1")
    cache.delete(f"schedule-shadow:{school.pk}")
    sent = []
    monkeypatch.setattr(tasks.shadow_schedule_v2_task, "delay", lambda *a, **k: sent.append(a))

    first = tasks.request_shadow_run(school)
    second = tasks.request_shadow_run(school)

    assert first == {"queued": True}
    assert second == {"queued": False, "reason": "already_requested"}
    assert len(sent) == 1
    cache.delete(f"schedule-shadow:{school.pk}")


def test_the_task_carries_a_time_limit_and_is_not_scheduled_periodically():
    from django.conf import settings

    assert tasks.shadow_schedule_v2_task.soft_time_limit
    assert tasks.shadow_schedule_v2_task.time_limit > tasks.shadow_schedule_v2_task.soft_time_limit
    scheduled = {entry["task"] for entry in getattr(settings, "CELERY_BEAT_SCHEDULE", {}).values()}
    assert "operations.shadow_schedule_v2" not in scheduled, "يطلبه المالكُ يدوياً لا جدولةً"
