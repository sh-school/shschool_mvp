"""مهمّةُ توليد اقتراحات المخالفة (W-20261013-034) — عملُ خلفيّةٍ لا يُستدعى من طلب؛ جدولتُها معطَّلةٌ حتى `CONDUCT_PROPOSALS_BEAT=1`."""

from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

from core.celery_tasks import school_rls_scope

logger = logging.getLogger(__name__)


@shared_task(name="wings.generate_conduct_proposals")
def generate_conduct_proposals_task() -> dict[str, int]:
    """مدرسةً مدرسةً بنطاق RLS؛ مدرسةٌ معطوبةٌ تُسجَّل ولا تُسقط غيرَها."""
    from core.models import School
    from wings.conduct_services import generate_due

    today = timezone.localdate()
    created = failed = 0
    for school in School.objects.filter(is_active=True).iterator(chunk_size=100):
        try:
            with school_rls_scope(school.id):
                created += generate_due(school, today)["created"]
        except Exception:  # noqa: BLE001 — مدرسةٌ معطوبةٌ لا تُسقط غيرَها
            failed += 1
            logger.exception("generate_conduct_proposals: تعذّر في المدرسة %s", school.pk)
    return {"created": created, "failed_schools": failed}
