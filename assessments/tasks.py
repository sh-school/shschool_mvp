"""مهامُّ Celery للتقييم — إعادةُ حساب الشعبة خلفيّاً (W-20261027-029).

كان `recalculate_class` متزامناً داخل الطلب (يتجاوز 300ms ويحجب العامل). الطابورُ من الإعداد (`EXPORT_JOB_QUEUE`) لا حرفيّاً
(وإلّا ضاعت المهمّةُ في شجرة العمل؛ `core/exports/services.py`). علَمُ «قيد الحساب» في الـcache يقرؤه كشفُ الدرجات.
"""

from __future__ import annotations

import logging

from celery import current_app, shared_task
from django.conf import settings
from django.core.cache import cache

from core.celery_tasks import school_rls_scope

logger = logging.getLogger(__name__)

#: أطولُ ما يبقى علَمُ «قيد الحساب» إن سقط العاملُ قبل أن يمسحه.
RECALC_FLAG_TTL = 300


def recalc_flag_key(setup_id: object) -> str:
    return f"assessments:recalc:{setup_id}"


def is_recalculating(setup_id: object) -> bool:
    return bool(cache.get(recalc_flag_key(setup_id)))


TASK_NAME = "assessments.recalculate_class"


@shared_task(name=TASK_NAME, soft_time_limit=150, time_limit=170)
def recalculate_class_task(setup_id: str, actor_id: str | None = None) -> dict:
    from assessments.models import SubjectClassSetup
    from assessments.services import GradeService
    from core.models import CustomUser

    setup = (
        SubjectClassSetup.objects.select_related("school", "class_group")
        .filter(pk=setup_id)
        .first()
    )
    if setup is None:
        cache.delete(recalc_flag_key(setup_id))
        logger.warning("recalc_class_missing setup=%s", setup_id)
        return {"ok": False, "code": "setup_not_found"}
    try:
        with school_rls_scope(setup.school_id):
            actor = CustomUser.objects.filter(pk=actor_id).first() if actor_id else None
            GradeService.recalculate_full_class(setup, actor=actor)
    except Exception:  # noqa: BLE001 — رمزٌ ثابتٌ لا نصُّ استثناء (كما في core/exports/runner.py)
        logger.error("recalc_class_failed setup=%s code=failed", setup_id)
        return {"ok": False, "code": "failed"}
    finally:
        cache.delete(recalc_flag_key(setup_id))
    return {"ok": True}


def dispatch_recalculate_class(setup_id: object, actor_id: object = None) -> bool:
    """يرفع العلَمَ ثمّ يرسل المهمّةَ على قائمة `EXPORT_JOB_QUEUE` إن ضُبطت وإلّا الافتراضيّة.

    يُرجع False دون إرسالٍ إن كانت إعادةُ الحساب جاريةً لهذه الشعبة (ضغطةٌ مكرّرة)."""
    if not cache.add(recalc_flag_key(setup_id), "1", timeout=RECALC_FLAG_TTL):
        return False
    queue = getattr(settings, "EXPORT_JOB_QUEUE", None)
    # بالاسم من سجلّ المهامّ (يحترم eager في التطوير) لا بالمرجع المباشر: وإلّا عدّت سقّاطةُ الطبقات ORM جسمِ المهمّة على العرض.
    current_app.tasks[TASK_NAME].apply_async(
        args=(str(setup_id), str(actor_id) if actor_id else None),
        **({"queue": queue} if queue else {}),
    )
    return True
