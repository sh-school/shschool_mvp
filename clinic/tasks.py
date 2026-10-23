"""مهمّةُ العيادة الخلفيّة (W-20261020-030): إغلاقُ الزيارات المنسيّة بعد ثلاث ساعات.

عملُ خلفيّةٍ لا يُستدعى من طلب. **الجدولةُ معطَّلةٌ افتراضياً** — `CLINIC_AUTOCLOSE_BEAT=1` وحدَه يُدخلها
`beat_schedule` (`autoclose_beat.py`) بعد إعادة نشر خدمة beat بأمر المالك، على نمط `TEACHER_ALERTS_BEAT`.
"""

from __future__ import annotations

import logging

from celery import shared_task

from core.celery_tasks import school_rls_scope

logger = logging.getLogger(__name__)


@shared_task(name="clinic.auto_close_stale_visits")
def auto_close_stale_visits_task() -> dict[str, int]:
    """مدرسةً مدرسةً بنطاق RLS؛ مدرسةٌ معطوبةٌ تُسجَّل ولا تُسقط غيرَها."""
    from clinic.services import ClinicService
    from core.models import School

    closed = failed = 0
    for school in School.objects.filter(is_active=True).iterator(chunk_size=100):
        try:
            with school_rls_scope(school.id):
                closed += ClinicService.auto_close_stale(school)
        except Exception:  # noqa: BLE001 — مدرسةٌ معطوبةٌ لا تُسقط غيرَها
            failed += 1
            logger.exception("auto_close_stale_visits: تعذّر في المدرسة %s", school.pk)
    return {"closed": closed, "failed_schools": failed}


@shared_task(name="clinic.alert_supply_expiry")
def alert_supply_expiry_task() -> dict[str, int]:
    """تنبيهُ الممرّضين بصلاحية المستلزمات (W-20261020-040): مدرسةً مدرسةً بنطاق RLS، وثابتُ التكرار."""
    from clinic.supplies import alert_nurses
    from core.models import School

    created = failed = 0
    for school in School.objects.filter(is_active=True).iterator(chunk_size=100):
        try:
            with school_rls_scope(school.id):
                created += alert_nurses(school)
        except Exception:  # noqa: BLE001 — مدرسةٌ معطوبةٌ لا تُسقط غيرَها
            failed += 1
            logger.exception("alert_supply_expiry: تعذّر في المدرسة %s", school.pk)
    return {"created": created, "failed_schools": failed}
