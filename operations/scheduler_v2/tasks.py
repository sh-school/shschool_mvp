"""tasks.py — عاملُ توليد V2: الحلُّ في Celery لا في الويب (>300ms)، idempotent."""

from __future__ import annotations

import logging
import os
import time

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

from core.celery_tasks import school_rls_scope
from operations.scheduler_v2.limits import GENERATION_HARD_TIME_LIMIT, GENERATION_SOFT_TIME_LIMIT

logger = logging.getLogger(__name__)


@shared_task(
    name="operations.generate_schedule_v2",
    bind=True,
    max_retries=0,
    soft_time_limit=GENERATION_SOFT_TIME_LIMIT,
    time_limit=GENERATION_HARD_TIME_LIMIT,
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
        failed = runner.RunResult(False, None, None, message, "timeout")
        runner.fail_generation(generation, failed)
        _finish(generation, failed)
        return {"ok": False, "reason": "soft_time_limit"}
    except Exception:  # noqa: BLE001 — يُسجَّل للمشغّل ويُقال للمستخدم عامّاً
        logger.exception("generate_schedule_v2: فشل التوليد %s", generation_id)
        message = "خطأ غير متوقَّع في توليد V2 — راجع سجلّ المشغّل"
        failed = runner.RunResult(False, None, None, message, "error")
        runner.fail_generation(generation, failed)
        _finish(generation, failed)
        return {"ok": False, "reason": "exception"}
    _finish(generation, result)
    return {"ok": result.ok, "reason": result.reason}


def _finish(generation, result):
    """ما كانت V1 تفعله بعد الحلّ: مؤشّراتُ المختبر تُحفظ، ومن ضغط الزرَّ يُخبَر بالمصير."""
    from operations.models import ScheduleGeneration
    from operations.tasks import _notify_generation_done

    generation = ScheduleGeneration.objects.select_related("school").get(pk=generation.pk)
    if not result.ok:
        _notify_generation_done(
            generation, ok=False, summary=generation.error_message or result.message
        )
        return
    try:
        from operations.schedule_lab import store_metrics

        store_metrics(generation)
    except Exception:  # noqa: BLE001 — القياسُ لا يُسقط توليداً ناجحاً
        logger.exception("schedule_lab: تعذّر حسابُ المؤشرات للتوليد %s", generation.pk)
    _notify_generation_done(
        generation,
        ok=True,
        summary=f"{generation.total_slots_created} حصّة في مسودّةٍ جاهزةٍ للمراجعة",
    )


# ───────────────────────── التشغيلُ الظلّيّ (W-20261003-018، قرار D-318م) ─────────────────────────
#
# يشغّل V2 وحدَه على مدخلات المدرسة الحاليّة ويقارن ناتجَه بالجدول المعتمَد بمؤشّرات W-008 نفسِها ويقيس الزمن.
# لا ينشر ولا يترك حصّةً ولا صفَّ توليدٍ في القاعدة ولا يلمس الجدول الحيّ (الخطّ الأحمر D-381م): الحصصُ تُكتب
# داخل معاملةٍ تُتراجَع دائماً لتقيسها أداةُ المقارنة، والنتيجةُ تُحفظ ملفَّ JSON بالقيم (بلا أسماء) في التخزين
# الافتراضيّ بمفتاح معرّف التشغيل. ولا يعمل في الإنتاج إلّا بقول المالك: غيابُ `SCHEDULE_SHADOW_ALLOWED=1` يرفضه.

SHADOW_ENV = "SCHEDULE_SHADOW_ALLOWED"
SHADOW_DIR = "schedule_shadow"


class ShadowNotAllowedError(RuntimeError):
    """طلبُ تشغيلٍ ظلّيٍّ بلا إذنٍ صريح في البيئة."""


class _Rollback(Exception):  # noqa: N818 — إشارةُ تراجعٍ داخليّة لا خطأ
    """يُرمى لإلغاء معاملة القياس فلا يبقى منها شيء."""


def shadow_allowed() -> bool:
    return os.environ.get(SHADOW_ENV) == "1"


def shadow_path(school_id, run_id) -> str:
    return f"{SHADOW_DIR}/{school_id}/{run_id}.json"


def _compare_in_rollback(school, academic_year, result, inputs) -> dict:
    """يكتب حصصَ الناتج داخل معاملةٍ يُتراجَع عنها دائماً ويقارنها بالمعتمَد بأداة W-008 نفسِها."""
    from django.db import transaction

    from operations.models import ScheduleGeneration, ScheduleSlot
    from operations.schedule_comparison import compare_generation
    from operations.scheduler_v2 import runner

    comparison: dict = {}
    try:
        with transaction.atomic():
            probe = ScheduleGeneration.objects.create(
                school=school, academic_year=academic_year, status="failed"
            )
            ScheduleSlot.objects.bulk_create(
                runner.draft_slot_rows(probe, result, inputs), batch_size=500
            )
            comparison = compare_generation(probe)
            raise _Rollback
    except _Rollback:
        pass
    return comparison


def store_shadow_report(school, run_id, report: dict) -> str:
    """يحفظ تقريرَ التشغيل ملفَّ JSON في التخزين الافتراضيّ ويُرجع مسارَه؛ لا جدولَ ولا هجرة."""
    import json

    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage

    body = json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True)
    return default_storage.save(shadow_path(school.pk, run_id), ContentFile(body.encode("utf-8")))


def read_shadow_report(school_id, run_id) -> dict | None:
    import json

    from django.core.files.storage import default_storage

    path = shadow_path(school_id, run_id)
    if not default_storage.exists(path):
        return None
    with default_storage.open(path) as handle:
        return json.loads(handle.read().decode("utf-8"))


def run_shadow(school, academic_year, config, **hooks) -> dict:
    """يشغّل V2 ظلّيّاً ويسجّل النتيجةَ والزمن؛ `hooks` (inputs/builder/solver…) للاختبار فقط."""
    import uuid

    from django.utils import timezone

    from operations.scheduler_v2 import runner

    run_id = uuid.uuid4().hex
    started_at, started = timezone.now(), time.monotonic()
    inputs = None
    try:
        result, inputs = runner.run(school, academic_year, config, **hooks)
    except runner.SchoolBusyError as error:
        result = runner.RunResult(False, None, None, str(error), "busy")
    except runner.ContractMissingError as error:
        result = runner.RunResult(False, None, None, str(error), "no_model")
    comparison = _compare_in_rollback(school, academic_year, result, inputs) if result.ok else None
    report = result.report
    outcome = {
        "run_id": run_id,
        "school_id": str(school.pk),
        "academic_year": academic_year,
        "engine": runner.ENGINE,
        "state": "ok" if result.ok else result.reason,
        "solver_status": report.status if report else None,
        "slots": len(report.slots) if report else 0,
        "unplaced": report.unplaced if report else None,
        "solver_seconds": round(report.seconds, 2) if report else None,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "seed": config.seed,
        "workers": config.workers,
        "max_seconds": config.max_seconds,
        "started_at": started_at.isoformat(),
        "environment": os.environ.get("RAILWAY_ENVIRONMENT_NAME", "local"),
        "comparison": comparison,
    }
    path = store_shadow_report(school, run_id, outcome)
    return {"ok": result.ok, "reason": result.reason, "path": path, **outcome}


@shared_task(
    name="operations.shadow_schedule_v2",
    bind=True,
    max_retries=0,
    soft_time_limit=GENERATION_SOFT_TIME_LIMIT,
    time_limit=GENERATION_HARD_TIME_LIMIT,
)
def shadow_schedule_v2_task(
    self, school_id, academic_year=None, seed=None, workers=None, max_seconds=None
):
    """مهمّةُ التشغيل الظلّيّ بحدّ زمن: تكتمل أو تتوقّف بلا أثرٍ على التوليد الحيّ ولا على المعتمَد."""
    import uuid

    from core.academic_calendar import academic_year_for_school
    from core.models import School
    from operations.scheduler_v2 import runner

    if not shadow_allowed():
        return {"ok": False, "reason": "not_allowed"}
    school = School.objects.filter(pk=school_id).first()
    if school is None:
        return {"ok": False, "reason": "school_not_found"}
    year = academic_year or academic_year_for_school(school)
    config = runner.SolverConfig(
        seed=runner.DEFAULT_SEED if seed is None else seed,
        workers=runner.DEFAULT_WORKERS if workers is None else workers,
        max_seconds=runner.DEFAULT_MAX_SECONDS if max_seconds is None else max_seconds,
    )
    try:
        with school_rls_scope(school.pk):
            return run_shadow(school, year, config)
    except SoftTimeLimitExceeded:
        run_id = uuid.uuid4().hex
        store_shadow_report(
            school,
            run_id,
            {"run_id": run_id, "school_id": str(school.pk), "state": "soft_time_limit"},
        )
        return {"ok": False, "reason": "soft_time_limit", "run_id": run_id}


def request_shadow_run(school, academic_year=None, **config) -> dict:
    """يطلب تشغيلاً ظلّيّاً واحداً للمدرسة (idempotent بالساعة) — لا جدولةَ دوريّةَ له: يطلبه المالكُ يدويّاً."""
    from django.core.cache import cache

    if not shadow_allowed():
        raise ShadowNotAllowedError(f"التشغيلُ الظلّيّ يحتاج {SHADOW_ENV}=1 بقول المالك")
    if not cache.add(f"schedule-shadow:{school.pk}", 1, GENERATION_SOFT_TIME_LIMIT):
        return {"queued": False, "reason": "already_requested"}
    shadow_schedule_v2_task.delay(str(school.pk), academic_year, **config)
    return {"queued": True}
