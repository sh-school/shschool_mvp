"""تجميدُ التواصل مع أولياء الأمور في طبقة الإشعارات (W-20261008-013، D-268م وD-272م).

مفتاحٌ واحد في `core.parents_freeze`؛ وهنا ما تحتاجه مهامُّ الإشعارات والـHub منه، مجموعاً في وحدةٍ
واحدة كي لا تتضخّم `tasks.py` و`hub.py` (سقّاطةُ حجم الملفّات). لا شيءَ هنا يحذف أو يغيّر حالةَ سجلّ.

في `hub.dispatch` يتقدّم التجميدُ على كلّ فحصٍ بعده، ومنه `_MANDATORY_SERVICE_EVENTS` التي تتخطّى
الموافقة: فلا يُكتب لوليّ أمرٍ مجمَّد إشعارُ منصّة ولا قناةٌ خارجيّة، والكادرُ يستلم كالمعتاد.
"""

import logging
from collections.abc import Iterable
from typing import Any

from core.parents_freeze import (  # noqa: F401
    frozen_recipient,
    is_parent_only,
    parents_frozen,
    without_frozen_parents,
)

from . import quiet_hours

logger = logging.getLogger(__name__)

#: مدّةُ إعادة سؤال عنصرٍ مؤجَّلٍ لوليّ أمرٍ أثناء التجميد — لا تتجاوز قفزةَ الهدوء (45 د)
#: وإلا أُعيد تسليمُ Redis للمهمّة قبل موعدها فتكرّر.
FROZEN_RECHECK_SECONDS = int(quiet_hours.MAX_HOLD_HOP.total_seconds())


def channel_skip(
    channel: str, *, email: str | None = None, phone: str | None = None
) -> dict[str, str] | None:
    """نتيجةُ تخطّي مهمّة قناةٍ لعنوان وليّ أمرٍ مجمَّد؛ و`None` إن وجب الإرسال."""
    if frozen_recipient(email=email, phone=phone):
        # القناةُ والسببُ وحدَهما: لا بريدَ ولا هاتفَ ولا اسمَ ولا معرّفَ (PDPPL) — يكفي لعدّ ما حُجب.
        logger.info("تخطّي إرسال مجمَّد: القناة=%s السبب=parents_frozen", channel)
        return {"status": "skipped", "reason": "parents_frozen", "channel": channel}
    return None


def frozen_user(user: Any) -> bool:
    """مستلمٌ وليُّ أمرٍ خالصٌ والتواصلُ مجمَّد؟"""
    return parents_frozen() and is_parent_only(user)


def drop_frozen_subscribers(user_ids: Iterable[Any]) -> list[Any]:
    """معرّفاتُ المشتركين بعد استبعاد أولياء الأمور الخُلَّص؛ المشتركُ الكادرُ يبقى."""
    user_ids = list(user_ids)
    if not parents_frozen():
        return user_ids
    from core.models import CustomUser

    kept = {u.pk for u in without_frozen_parents(CustomUser.objects.filter(pk__in=user_ids))}
    return [uid for uid in user_ids if uid in kept]


def hold_frozen_item(task: Any, **kwargs: Any) -> dict[str, str]:
    """عنصرٌ مؤجَّلٌ بساعات الهدوء لوليّ أمر: لا يُرسل ولا يُحذف — يُعاد سؤالُه حتى الفكّ."""
    task.apply_async(kwargs=kwargs, countdown=FROZEN_RECHECK_SECONDS)
    return {"status": "held_parents_frozen"}
