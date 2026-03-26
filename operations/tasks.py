"""
operations/tasks.py
مهام Celery المُجدوَلة لنظام العمليات — توليد الحصص اليومية
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

الاستخدام:
    # يدوي (من shell أو view):
    generate_daily_sessions_task.delay()                  # كل المدارس
    generate_daily_sessions_task.delay(school_id="...")    # مدرسة واحدة

    # تلقائي (Celery Beat):
    يعمل يومياً الساعة 6:00 صباحاً (أحد–خميس) — مُعرَّف في celery.py
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="operations.generate_daily_sessions",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
)
def generate_daily_sessions_task(self, school_id=None):
    """
    توليد Session يومية من ScheduleSlot لجميع المدارس النشطة.

    - idempotent: get_or_create يمنع التكرار
    - يعمل عبر Celery Beat (أحد–خميس 6:00 صباحاً)
    - يُستدعى أيضاً يدوياً من شاشة الإدارة
    """
    try:
        from django.utils import timezone

        from core.models import School
        from operations.services import ScheduleService

        today = timezone.localdate()

        if school_id:
            schools = School.objects.filter(id=school_id, is_active=True)
        else:
            schools = School.objects.filter(is_active=True)

        total = 0
        for school in schools:
            count = ScheduleService.generate_daily_sessions(school, today)
            total += count
            if count > 0:
                logger.info(
                    "generate_daily_sessions: %d sessions for %s on %s",
                    count,
                    school.name,
                    today,
                )

        logger.info(
            "generate_daily_sessions_task complete: %d sessions total on %s",
            total,
            today,
        )
        return {"date": str(today), "total_sessions": total}

    except Exception as exc:
        logger.exception("generate_daily_sessions_task error: %s", exc)
        raise self.retry(exc=exc)
