import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="decisions_registry.check_drift", ignore_result=True)
def check_drift_task() -> None:
    """فحصٌ يوميٌّ محلّيّ لبصمات جدول القرارات؛ الانجرافُ يُسجَّل خطأً فيصل Sentry."""
    from .services import check_drift

    drifted = check_drift()
    if drifted:
        logger.error("decisions_registry: انجرافُ %d قراراً (أوّلها %s)", len(drifted), drifted[0])
