"""[SCHEDULE] لا يبقى صفُّ توليدٍ «يجري» إلى الأبد، ولا يُسقط خطأُ قياسٍ اعتماداً كاملاً.

الموجةُ الأولى لتجويد التوليد (G1، تقرير SWOT 2026-09-28):
- F-09: فشلُ الحفظ داخل معاملة `generate_schedule` كان يُعيد الكائنَ نفسَه بلا تغييرٍ في حالته
  (لأنّ `generation` مُرَّرٌ من الطلب سلفاً، فليس None أبداً)، فيسقط شرطُ `operations/tasks.py`
  الوحيدُ ويبقى الصفُّ «يجري» بلا نهاية — يُنسَب لاحقاً إلى توقّف العامل.
- F-15: خطأُ قاعدة بياناتٍ داخل `store_metrics` عند الاعتماد (`operations/services/schedule.py`)
  كان يُفسد معاملةَ `approve_generation` الخارجيّةَ صامتاً بلا نقطة حفظٍ مستقلّة، فيتراجع
  الاعتمادُ كلُّه بخطإٍ لا صلةَ له بالقياس.
"""

import pytest

from operations.models import ScheduleGeneration
from operations.services.schedule import ScheduleService

YEAR = "2026-2027"


# ── F-09: الصفُّ العالق بعد فشل الحفظ ────────────────────────────────────────


def _fake_result(generation, *, errors, saved: bool):
    """يحاكي عودةَ `generate_schedule`: `saved` يتحكّم هل تحوّلت حالةُ الصفّ فعلاً."""
    if saved:
        ScheduleGeneration.objects.filter(pk=generation.pk).update(status="draft")
    return {
        "success": not errors,
        "grid": None,
        "quality": {
            "score": 0,
            "total_slots": 0,
            "total_required": 0,
            "placed_ratio": 0,
            "violations": {},
        },
        "generation": generation,  # نفسُ الكائن الممرَّر — أبداً None في هذا المسار
        "errors": errors,
        "tasks": [],
        "leftover_tasks": [],
        "elapsed_ms": 5,
        "stopped": False,
    }


@pytest.mark.django_db
def test_a_failed_save_marks_the_row_failed_instead_of_leaving_it_running(school, monkeypatch):
    """فشلُ الحفظ داخل المعاملة (استثناءٌ أو صفرُ حصصٍ): الصفُّ ينتقل إلى «فشل» لا يبقى «يجري»."""
    from operations.tasks import generate_smart_schedule_task

    gen = ScheduleGeneration.objects.create(school=school, academic_year=YEAR, status="queued")
    error = "فشل حفظ الجدول المولَّد — سُجّلت التفاصيلُ للمشغّل."
    monkeypatch.setattr(
        "operations.scheduler.generate_schedule",
        lambda *a, **kw: _fake_result(gen, errors=[error], saved=False),
    )

    outcome = generate_smart_schedule_task.run(str(gen.pk))

    gen.refresh_from_db()
    assert outcome == {"ok": False, "reason": "not_saved"}
    assert gen.status == "failed"
    assert gen.error_message == error
    assert gen.finished_at is not None


@pytest.mark.django_db
def test_a_successful_save_with_leftover_errors_stays_a_draft(school, monkeypatch):
    """توليدٌ فيه حصصٌ متعذّرةٌ (خطأُ توزيعٍ لا خطأَ حفظ) يُحفظ مسوَّدةً بخطئه — لا يُقفل «فشل»."""
    from operations.tasks import generate_smart_schedule_task

    gen = ScheduleGeneration.objects.create(school=school, academic_year=YEAR, status="queued")
    error = "تعذّر وضع: الشعبة 9/1 — الرياضيات (خانتان)."
    monkeypatch.setattr(
        "operations.scheduler.generate_schedule",
        lambda *a, **kw: _fake_result(gen, errors=[error], saved=True),
    )

    outcome = generate_smart_schedule_task.run(str(gen.pk))

    gen.refresh_from_db()
    assert outcome["ok"] is False and outcome["failed"] == 1
    assert gen.status == "draft"
    assert gen.error_message == error


@pytest.mark.django_db
def test_a_clean_save_marks_neither_failed_nor_stuck(school, monkeypatch):
    from operations.tasks import generate_smart_schedule_task

    gen = ScheduleGeneration.objects.create(school=school, academic_year=YEAR, status="queued")
    monkeypatch.setattr(
        "operations.scheduler.generate_schedule",
        lambda *a, **kw: _fake_result(gen, errors=[], saved=True),
    )

    outcome = generate_smart_schedule_task.run(str(gen.pk))

    gen.refresh_from_db()
    assert outcome["ok"] is True
    assert gen.status == "draft"
    assert gen.error_message == ""


# ── F-15: نقطةُ حفظٍ لقياس الاعتماد ───────────────────────────────────────────


@pytest.mark.django_db
def test_a_metrics_failure_at_approval_does_not_roll_back_the_whole_approval(school, monkeypatch):
    """خطأٌ داخل `store_metrics` لا يُسقط تفعيلَ الحصص ولا انتقالَ الحالة إلى «معتمَد»."""

    def boom(_gen):
        raise RuntimeError("قياسٌ معطوبٌ عمداً للاختبار")

    monkeypatch.setattr("operations.schedule_lab.store_metrics", boom)

    gen = ScheduleGeneration.objects.create(school=school, academic_year=YEAR, status="draft")

    result = ScheduleService.approve_generation(gen, notify=False)

    gen.refresh_from_db()
    assert gen.status == "approved"
    assert result["notified"] == 0


@pytest.mark.django_db
def test_a_healthy_metrics_call_still_runs_at_approval(school, monkeypatch):
    """الحرّاسُ لا يُطفئان القياسَ السليم — `store_metrics` تُستدعى فعلاً حين لا عطب."""
    calls = []
    monkeypatch.setattr(
        "operations.schedule_lab.store_metrics", lambda gen: calls.append(gen.pk) or {}
    )

    gen = ScheduleGeneration.objects.create(school=school, academic_year=YEAR, status="draft")

    ScheduleService.approve_generation(gen, notify=False)

    assert calls == [gen.pk]
