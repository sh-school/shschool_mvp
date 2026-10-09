"""tasks.py — عاملُ توليد V2: الحلُّ في Celery لا في الويب (>300ms)، idempotent."""

from __future__ import annotations

import logging

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

from core.celery_tasks import school_rls_scope

logger = logging.getLogger(__name__)


@shared_task(
    name="operations.generate_schedule_v2",
    bind=True,
    max_retries=0,
    soft_time_limit=3600,
    time_limit=3660,
)
def generate_schedule_v2_task(
    self,
    generation_id,
    seed=None,
    workers=None,
    max_seconds=None,
    max_minutes=None,
    relaxations=None,
):
    """يلتقط صفَّ توليدٍ «في الانتظار» ويحلّه. التقاطٌ مكرَّرٌ لرسالةٍ واحدةٍ يُتخطّى (لا يُعاد على نتيجةٍ قائمة)."""
    from operations.models import ScheduleGeneration
    from operations.scheduler_v2 import runner

    generation = (
        ScheduleGeneration.objects.select_related("school").filter(pk=generation_id).first()
    )
    if generation is None:
        return {"ok": False, "reason": "generation_not_found"}
    claimed = ScheduleGeneration.objects.filter(
        pk=generation.pk, status__in=ScheduleGeneration.PENDING_STATUSES
    ).update(status="running")
    if not claimed:
        return {"ok": False, "reason": "not_pending"}
    generation.status = "running"

    if max_minutes:
        max_seconds = max_minutes * 60
    config = runner.SolverConfig(
        seed=runner.DEFAULT_SEED if seed is None else seed,
        workers=runner.DEFAULT_WORKERS if workers is None else workers,
        max_seconds=runner.DEFAULT_MAX_SECONDS if max_seconds is None else max_seconds,
        relaxations=tuple(sorted((relaxations or {}).items())),
    )
    try:
        with school_rls_scope(generation.school_id):
            result = runner.run_generation(generation, config)
    except SoftTimeLimitExceeded:
        message = "تجاوز العاملُ الزمنَ المسموح"
        runner.fail_generation(generation, runner.RunResult(False, None, None, message, "timeout"))
        return {"ok": False, "reason": "soft_time_limit"}
    except Exception:  # noqa: BLE001 — يُسجَّل للمشغّل ويُقال للمستخدم عامّاً
        logger.exception("generate_schedule_v2: فشل التوليد %s", generation_id)
        message = "خطأ غير متوقَّع في توليد V2 — راجع سجلّ المشغّل"
        runner.fail_generation(generation, runner.RunResult(False, None, None, message, "error"))
        return {"ok": False, "reason": "exception"}
    return {"ok": result.ok, "reason": result.reason}
