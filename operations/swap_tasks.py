"""مهمّةُ التبديل الخلفيّة (W-20261123-002): إلغاءُ الطلبات المعلّقة المنتهية.

عملُ خلفيّةٍ لا يُستدعى من طلب. **الجدولةُ معطَّلةٌ افتراضياً** — `SWAP_EXPIRY_BEAT=1` وحدَه يُدخلها
`beat_schedule` (`swap_expiry_beat.py`) بأمر المالك، على نمط `CLINIC_AUTOCLOSE_BEAT`.
"""

from __future__ import annotations

import logging

from celery import shared_task

from core.celery_tasks import school_rls_scope

logger = logging.getLogger(__name__)


@shared_task(name="operations.expire_stale_swaps")
def expire_stale_swaps_task() -> dict[str, int]:
    """مدرسةً مدرسةً بنطاق RLS؛ مدرسةٌ معطوبةٌ تُسجَّل ولا تُسقط غيرَها."""
    from core.models import School
    from operations.services.swap import SwapService

    cancelled = failed = 0
    for school in School.objects.filter(is_active=True).iterator(chunk_size=100):
        try:
            with school_rls_scope(school.id):
                cancelled += SwapService.expire_stale_swaps(school)
        except Exception:  # noqa: BLE001 — مدرسةٌ معطوبةٌ لا تُسقط غيرَها
            failed += 1
            logger.exception("expire_stale_swaps: تعذّر في المدرسة %s", school.pk)
    return {"cancelled": cancelled, "failed_schools": failed}
