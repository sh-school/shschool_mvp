"""كشفُ الدمج المتعطّل (W-20261022-011، المرحلة 1 من نقل المضخّة إلى كود المنصّة) — يقرأ GitHub وحدَه ولا يمسّ الدفتر.

المضخّةُ المحلّيّة تعمل بخطّاف الجلسات فتتوقّف عند الخمول (فجوتا 65 و75 دقيقة)، فيبقى طلبٌ جاهزٌ للدمج معلَّقاً ساعاتٍ دون أن يراه أحد.
هذا المجمِّعُ يعمل على جدولة العامل (مع مجمِّعات GitHub) فيكتشف حالتَين من الطلبات المفتوحة غيرِ المسوّدة:

- `stalled`: حالتُه CLEAN (`mergeable_state`) **والدمجُ التلقائيُّ مفعَّلٌ** ومرّ أكثرُ من `STALL_HOURS` بلا تحديثٍ — ما كان ينبغي أن يبقى.
- `unarmed`: حالتُه CLEAN **والدمجُ التلقائيُّ غيرُ مفعَّل** ومرّ أكثرُ من `STALL_HOURS` — فأيُّ ✔ سجّلته المضخّةُ لدمجه كاذبٌ
  (`autoMergeRequest` فارغ، وهو عينُ عطل W-20261022-009).

يكتب **تنبيهاً** (إشعارَ جرسٍ للمطوّر عبر `alerts.notify`) لا حالةَ لوحةٍ ولا شيئاً في الدفتر؛ ويكرّره كلَّ `RENOTIFY_SECONDS` لا كلَّ دورة،
ويُصفَّر ما إن يزول التعطّل. المصدرُ أرقامٌ وتصنيفاتٌ فقط: رقمُ الطلب لا عنوانَه ولا فرعَه ولا كاتبَه (المستودعُ عامّ).
المجمِّعُ لا يدمج ولا يفعّل الدمجَ التلقائيّ (ذلك المرحلةُ 2 وقرارُ رمز GitHub للمالك).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from django.core.cache import cache

from command_center import alerts
from command_center.collectors import github, queue

logger = logging.getLogger(__name__)

STALL_HOURS = 1
RENOTIFY_SECONDS = 6 * 3600
STATE_KEY = "qcc:flow_merge_stall"
_STATE_TTL = 7 * 24 * 3600
PANEL = "flow_merge_stall"
MAX_PULLS = 12


def classify(number: int, state: str, armed: bool, idle_hours: float | None) -> str | None:
    """`stalled` أو `unarmed` أو None (سليم) — لا حكمَ بلا عمرٍ معروف."""
    if state != "clean" or idle_hours is None or idle_hours <= STALL_HOURS:
        return None
    return "stalled" if armed else "unarmed"


def scan(now: float) -> dict[str, list[int]] | None:
    """رقماً الطلباتِ العالقة حسب النوع، أو None إن تعذّر GitHub (فلا يُصفَّر ما سبق ولا يُنذر)."""
    opened = github.fetch(queue.OPEN_PATH, queue.reduce_open)
    if opened is None:
        return None
    found: dict[str, list[int]] = {"stalled": [], "unarmed": []}
    for number, _sha, draft, armed, updated in opened["rows"][:MAX_PULLS]:
        if draft:
            continue
        detail = github.fetch(f"pulls/{number}", queue.reduce_detail)
        if detail is None:
            continue
        idle = None if updated is None else max(0.0, (now - float(updated)) / 3600)
        kind = classify(number, detail["state"], armed, idle)
        if kind:
            found[kind].append(number)
    return found


def _text(found: dict[str, list[int]]) -> tuple[str, str]:
    parts = []
    if found["stalled"]:
        parts.append(
            "جاهزٌ ودمجُه التلقائيّ مفعَّلٌ لكنّه لم يُدمج: " + "، ".join(f"#{n}" for n in found["stalled"])
        )
    if found["unarmed"]:
        parts.append(
            "جاهزٌ بلا دمجٍ تلقائيٍّ مفعَّل (أيُّ ✔ له كاذب): "
            + "، ".join(f"#{n}" for n in found["unarmed"])
        )
    return "الدمج متعطّل: طلبٌ جاهزٌ ينتظر أكثرَ من ساعة", "؛ ".join(parts) + "."


def collect(now: float | None = None) -> list[str]:
    """يفحص ويُنذر عند ظهور التعطّل أو بقائه ست ساعات — يعيد أوصافَ ما أُرسل (للسجلّ والاختبار)."""
    moment = time.time() if now is None else now
    found = scan(moment)
    if found is None:
        return []
    stuck = sorted(found["stalled"] + found["unarmed"])
    state: dict[str, Any] = cache.get(STATE_KEY) or {}
    if not stuck:
        if state:
            cache.delete(STATE_KEY)
        return []
    if not alerts.enabled():
        return []
    same = state.get("pulls") == stuck
    if same and moment - float(state.get("last_sent", 0)) < RENOTIFY_SECONDS:
        return []
    title, body = _text(found)
    alerts.notify(title, body, PANEL, "urgent", moment)
    cache.set(STATE_KEY, {"pulls": stuck, "last_sent": moment}, _STATE_TTL)
    return ["renotified" if same else "fired"]


def safe_collect() -> list[str]:
    """`collect` بلا رفع — عطلُه لا يوقف دورةَ الجمع."""
    try:
        return collect()
    except Exception:  # noqa: BLE001
        logger.warning("command center: flow merge stall check failed", exc_info=True)
        return []
