"""staff_affairs/tasks.py — مهامُّ الحضور والانصراف المجدولة."""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from core.celery_tasks import school_rls_scope

logger = logging.getLogger(__name__)


@shared_task(name="staff_affairs.send_monthly_absence_notices")
def send_monthly_absence_notices_task() -> dict[str, int]:
    """أوّلَ كلّ شهر: تقريرُ أيام الغياب التي لم تُغطَّ عن الشهر السابق لكلّ موظّفٍ (سياسة 5.1).

    مدرسةً مدرسةً داخل نطاقها (RLS). وفي الإنتاج اليومَ لا مزوّدَ بريد فالإشعارُ داخل المنصّة
    يصل والبريدُ يُسجَّل «لم يُسلَّم» — انظر ``staff_affairs.notices``.
    """
    from core.models import School
    from staff_affairs.notices import send_monthly_absence_notices

    previous = timezone.localdate().replace(day=1) - timedelta(days=1)
    total = 0
    for school in School.objects.filter(is_active=True).iterator(chunk_size=100):
        with school_rls_scope(school.id):
            notified = send_monthly_absence_notices(school, previous.year, previous.month)
        total += notified
        logger.info("school_id=%s absence_notices=%d", school.id, notified)
    return {"notified": total}
