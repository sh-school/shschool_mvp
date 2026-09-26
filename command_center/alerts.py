"""التنبيهُ الحيّ عند الأحمر — إشعارٌ في جرس المنصّة لمطوّرها (QCC-03، قرارُ المالك 2026-09-27: حيٌّ الآن لا تجريبيّ).

**الأحمرُ وحدَه يُنذر** (الأصفرُ صفحةٌ لا إشعار). آلةُ حالةٍ لكلّ لوحةٍ في الـcache:

- أحمرُ يستمرّ دقيقتين متّصلتين (دورتا جمعٍ) ← **إشعارٌ عاجل** («تأكيد»: ومضةُ جمعٍ واحدةٌ لا تُنذر).
- ما دامت حمراءَ يُكرَّر الإشعارُ كلَّ ست ساعات (لا كلَّ دقيقة).
- عودتُها من الأحمر ← إشعارٌ واحدٌ «خرجت من الخطر»، وتُصفَّر الحالة.
- **سقفٌ 12 إشعاراً في اليوم لكلّ مطوّر** فلا يُغرقه انفجارٌ من اللوحات.
- «غيرُ معلوم» ليس أحمرَ ولا عودةً: لا يُنذر ولا يُصفّر حالةَ لوحةٍ حمراء.

المستلمُ: كلُّ مطوّرٍ نشطٍ (superuser أو مجموعة `developers` — `core/developer_access.py`) له عضويّةٌ جاريةٌ في مدرسة (الإشعارُ الداخليُّ لمدرسة).
النصُّ ثوابتُ عربيّةٌ وعنوانُ اللوحة وجملتُها من المجمِّع — لا نصَّ من طرفٍ ثالث. يُكتب `InAppNotification` مباشرةً لا عبر `notifications/hub.py`
(ألف سطر بالضبط وغيرُ مسجَّلٍ في خطّ الأساس فلا يقبل سطراً). لا بريدَ ولا push (`UndeliveredEmailBackend`، لا VAPID).

**مفتاحُ الإيقاف**: `QCC_NOTIFY_ENABLED=false` في البيئة (أو `cache.set("qcc:kill", 1)` فوريّاً)؛ والإخفاقُ في الإرسال لا يُسقط الجمع.
لا يفعل المركزُ شيئاً آليّاً غيرَ الإشعار: لا نشرَ ولا رجوعاً ولا دمجاً ولا كتابةَ إنتاج.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from django.conf import settings
from django.core.cache import cache

from command_center import contract

logger = logging.getLogger(__name__)

CONFIRM_SECONDS = 120
RENOTIFY_SECONDS = 6 * 3600
DAILY_CAP = 12
KILL_KEY = "qcc:kill"
_STATE_TTL = 7 * 24 * 3600
PAGE_URL = "/command-center/"


def _state_key(panel: str) -> str:
    return f"qcc:alert:{panel}"


def enabled() -> bool:
    return bool(getattr(settings, "QCC_NOTIFY_ENABLED", True)) and not cache.get(KILL_KEY)


def recipients() -> list[tuple[Any, Any]]:
    """[(مطوّر، مدرسةُ عضويّته الجاريّة)] — من لا عضويّةَ جاريةً له لا يصله إشعارٌ داخليّ."""
    from django.contrib.auth import get_user_model
    from django.db.models import Q

    from core.developer_access import DEVELOPERS_GROUP
    from core.models import Membership

    users = (
        get_user_model()
        .objects.filter(is_active=True)
        .filter(Q(is_superuser=True) | Q(groups__name__iexact=DEVELOPERS_GROUP))
        .distinct()
    )
    found = []
    for user in users:
        membership = (
            Membership.objects.current()
            .filter(user=user, is_active=True)
            .select_related("school")
            .first()
        )
        if membership is not None:
            found.append((user, membership.school))
    return found


def _under_cap(user_id: Any, moment: float) -> bool:
    key = f"qcc:alert:cap:{user_id}:{time.strftime('%Y%m%d', time.gmtime(moment))}"
    cache.add(key, 0, 2 * 24 * 3600)
    try:
        return int(cache.incr(key)) <= DAILY_CAP
    except ValueError:
        return True


def notify(title: str, body: str, panel: str, priority: str, moment: float) -> int:
    """يكتب إشعاراً لكلّ مطوّرٍ تحت سقفه اليوميّ — يعيد عددَ من وصلهم. لا يرفع أبداً."""
    from notifications.models import InAppNotification

    sent = 0
    try:
        found = recipients()
    except Exception:  # noqa: BLE001 — الإنذارُ تابعٌ للجمع: عطلُه لا يوقفه
        logger.warning("command center: could not resolve recipients", exc_info=True)
        return 0
    for user, school in found:
        if not _under_cap(user.pk, moment):
            continue
        try:
            InAppNotification.objects.create(
                user=user,
                school=school,
                title=title,
                body=body,
                event_type="general",
                priority=priority,
                related_object_id=panel,
                related_url=PAGE_URL,
            )
            sent += 1
        except Exception:  # noqa: BLE001
            logger.warning("command center: notification failed", exc_info=True)
    return sent


def _red_text(panel: dict[str, Any]) -> tuple[str, str]:
    title = f"مركز قيادة الجودة: «{panel['title']}» في حالة خطر"
    headline = str(panel.get("headline") or "")
    lead = f"{headline} — " if headline else ""
    return title, f"{lead}افتح مركز القيادة لمعرفة السبب."


def _resolved_text(panel: dict[str, Any]) -> tuple[str, str]:
    return (
        f"مركز قيادة الجودة: «{panel['title']}» خرجت من حالة الخطر",
        "عادت اللوحةُ إلى ما دون الأحمر.",
    )


def evaluate(now: float | None = None) -> list[str]:
    """يقيّم لوحاتِ اللقطة الحاليّة ويُنذر عند الانتقال — يعيد أوصافَ ما أُرسل (لـ«ما جرى» في السجلّ والاختبار)."""
    if not enabled():
        return []
    moment = time.time() if now is None else now
    events: list[str] = []
    for panel in contract.read_panels(moment):
        key = panel["key"]
        status = panel["status"]
        state = cache.get(_state_key(key)) or {}
        if status == contract.BAD:
            if not state:
                cache.set(_state_key(key), {"state": "pending", "since": moment}, _STATE_TTL)
            elif state["state"] == "pending" and moment - state["since"] >= CONFIRM_SECONDS:
                title, body = _red_text(panel)
                notify(title, body, key, "urgent", moment)
                cache.set(
                    _state_key(key),
                    {"state": "firing", "since": state["since"], "last_sent": moment},
                    _STATE_TTL,
                )
                events.append(f"fired:{key}")
            elif state["state"] == "firing" and moment - state["last_sent"] >= RENOTIFY_SECONDS:
                title, body = _red_text(panel)
                notify(title, body, key, "urgent", moment)
                cache.set(_state_key(key), {**state, "last_sent": moment}, _STATE_TTL)
                events.append(f"renotified:{key}")
        elif status != contract.UNKNOWN and state:
            if state["state"] == "firing":
                title, body = _resolved_text(panel)
                notify(title, body, key, "medium", moment)
                events.append(f"resolved:{key}")
            cache.delete(_state_key(key))
    return events


def safe_evaluate() -> list[str]:
    """`evaluate` بلا رفع — يُستدعى في نهاية كلّ دورة جمع."""
    try:
        return evaluate()
    except Exception:  # noqa: BLE001
        logger.warning("command center: alert evaluation failed", exc_info=True)
        return []
