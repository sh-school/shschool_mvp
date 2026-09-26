"""الجمعُ الذاتيّ عند غياب Beat — فلا تبقى اللوحاتُ «غيرَ معلومة» محلّيّاً ولا في بيئةٍ بلا جدولة.

الإنتاجُ يجمع بـBeat (`shschool/celery.py`)، أمّا التطويرُ المحلّيّ (docker بلا Beat) والمعاينةُ فلا. فحين تقرأ الصفحةُ لقطةً قديمةً
(أكثرَ من ضعفَي دورةِ مجمِّعها) أو خاليةً تُطلَق مهمّةُ الجمع من هنا مرّةً كلَّ نصف دقيقةٍ لكلّ مجموعة (قفلٌ في الـcache)، فالإنتاجُ
السليمُ لا يمرّ بهذا المسار أصلاً. والحسابُ **لا يجري في الطلب**: بعاملٍ حقيقيٍّ تُرسَل المهمّةُ إليه **بشرط أن يشاركنا الـcache**
(Redis)؛ أمّا في الوضع المتزامن (`CELERY_TASK_ALWAYS_EAGER`) أو حين يكون الـcache في ذاكرة العمليّة (`LocMemCache` في التطوير
المحلّيّ: كلُّ عمليّةٍ لها cache، فما يكتبه العاملُ لا يراه الويب) أو عند تعذّر الوسيط، يجري في خيطٍ خلفيٍّ يُغلق اتّصالَه بالقاعدة عند انتهائه.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from django.conf import settings
from django.core.cache import cache
from django.db import connections

from command_center import collectors, contract, tasks

logger = logging.getLogger(__name__)

LOCK_SECONDS = 30
#: دورةُ كلّ مجموعة (ثوانٍ) كما في جدول Beat — والقِدَمُ المقبولُ ضعفُها.
CADENCE = {"local": 60, "remote": 240}
GROUPS: dict[str, tuple[dict[str, collectors.Collector], Callable[[], object]]] = {
    "local": (collectors.LOCAL, tasks.collect_local),
    "remote": (collectors.REMOTE, tasks.collect_remote),
}


def _lock_key(group: str) -> str:
    return f"qcc:refresh:{group}"


def stale_groups(now: float | None = None) -> list[str]:
    """المجموعاتُ التي فيها لوحةٌ غيرُ مجموعةٍ أو أقدمُ من ضعفَي دورتها."""
    moment = time.time() if now is None else now
    panels = {panel["key"]: panel for panel in contract.read_panels(moment)}
    stale = []
    for group, (members, _) in GROUPS.items():
        limit = 2 * CADENCE[group]
        ages = [panels[key]["age_seconds"] for key in members if key in panels]
        if any(age is None or age > limit for age in ages):
            stale.append(group)
    return stale


def _in_thread(group: str) -> None:
    def work() -> None:
        try:
            collectors.run(GROUPS[group][0])
        finally:
            connections.close_all()

    threading.Thread(target=work, name=f"qcc-{group}", daemon=True).start()


def _worker_shares_our_cache() -> bool:
    """هل يرى الويبُ ما يكتبه العاملُ؟ لا في الوضع المتزامن ولا مع cache في الذاكرة أو بلا تخزين."""
    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        return False
    backend = str(settings.CACHES.get("default", {}).get("BACKEND", "")).lower()
    return not any(word in backend for word in ("locmem", "dummy"))


def _dispatch(group: str) -> None:
    if not _worker_shares_our_cache():
        _in_thread(group)
        return
    try:
        GROUPS[group][1].delay()  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 — الوسيطُ معطَّل: نجمع بأنفسنا بدل ترك اللوحات فارغة
        logger.warning("command center: broker unavailable, collecting in a thread", exc_info=True)
        _in_thread(group)


def ensure_fresh(now: float | None = None) -> list[str]:
    """يطلق جمعَ المجموعات القديمة (مرّةً لكلٍّ بقفل) — يعيد ما أُطلق. لا يرفع أبداً ولا يحسب في الطلب."""
    if not getattr(settings, "QCC_LAZY_REFRESH", True):
        return []
    launched = []
    try:
        for group in stale_groups(now):
            if cache.add(_lock_key(group), 1, LOCK_SECONDS):
                _dispatch(group)
                launched.append(group)
    except Exception:  # noqa: BLE001 — الجمعُ الذاتيّ تحسينٌ: عطلُه لا يُسقط الصفحة
        logger.warning("command center: lazy refresh failed", exc_info=True)
    return launched
