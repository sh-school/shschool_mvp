"""استقبالُ القياس الميدانيّ (Q-04) وتجميعُه — الجانبُ الخلفيّ لعقد `docs/rum_client_contract_2026-09.md`.

العميلُ `static/js/rum.js` يرسل حمولةً بثمانية حقولٍ بلا هويّة. وهذا الملفّ: **يتحقّق بصرامةٍ** (ما خالف المجالَ أو القوائمَ يُرمى صامتاً)، و**يجمّع** في عدّاداتِ
دلاءٍ ثابتةٍ في الـcache لكلّ (يوم، جهاز، مقياس) — فلا صفَّ خاماً ولا أثرَ لزيارةٍ بعينها، ولا جدولَ ولا RLS ولا وثيقةَ احتفاظ (العدّاداتُ تنتهي بعد تسعة أيّام).
ويُحسب p75 من الدلاء: **الحدُّ الأعلى للدلو** (تقديرٌ محافِظٌ لا يُخفي السوء).

الدلاءُ تطابق عتبات Core Web Vitals بلا كسر: LCP بـ250ms (جيّد ≤2500، ضعيف >4000)، وINP بـ50ms (200 و500)، وCLS بـ0.025 (0.1 و0.25) — فيقع كلُّ حدٍّ على حافّة دلو.

**ما لا يُخزَّن**: IP، وكيلُ المستخدم، الكوكيز، Referer، أيُّ معرّف، ولا `lay`/`nav`/`net` (تُتحقَّق ثمّ تُهمَل — الوثيقةُ تسمح بها لكنّ المجمَّعَ الأصغرَ أصغرُ أثراً؛ تُضاف حين يلزم).
حدٌّ عامٌّ 3000 حمولةٍ في الدقيقة يحمي الـcache من الإغراق. والانتقالُ بتبديل المحتوى لا يُنشئ تحميلاً: الأرقامُ لجلسة الاستعمال (حدودُ القياس في الوثيقة).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from django.core.cache import cache

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = 400
DEVICES = ("phone", "tablet", "desktop")
LAYOUTS = ("dashboard", "hub", "list", "detail", "form", "sheet", "report", "custom")
NAV = ("navigate", "reload", "back_forward", "prerender")
NET = ("slow-2g", "2g", "3g", "4g")
DAYS_KEPT = 8
_TTL = (DAYS_KEPT + 1) * 24 * 3600
RATE_PER_MINUTE = 3000
MIN_SAMPLE = 30
BAD_SAMPLE = 100


class Metric:
    """مقياسٌ بمجاله ودلائه وعتبتَيه: جيّد ≤ good، وضعيف > poor (Core Web Vitals)."""

    def __init__(
        self,
        key: str,
        maximum: float,
        cap: float,
        width: float,
        good: float,
        poor: float,
        unit: str,
    ):
        self.key, self.maximum, self.width = key, maximum, width
        self.good, self.poor, self.unit = good, poor, unit
        #: دلاءٌ حتى `cap` ثمّ دلوُ الفائض (ما فوقه) — فالمدى المقبولُ `maximum` أوسعُ من الدلاء
        self.count = round(cap / width)

    def bucket(self, value: float) -> int:
        return min(int(value // self.width), self.count)

    def upper(self, bucket: int) -> float:
        return round((bucket + 1) * self.width, 3)


METRICS = {
    "lcp": Metric("lcp", 60000, 10000, 250, 2500, 4000, "ms"),
    "inp": Metric("inp", 10000, 2000, 50, 200, 500, "ms"),
    "cls": Metric("cls", 10, 1.0, 0.025, 0.1, 0.25, ""),
}


def _number(value: Any, low: float, high: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if low <= value <= high else None


def parse(raw: bytes) -> dict[str, Any] | None:
    """الحمولةُ المقبولة أو None — نموذجٌ صارمٌ: نوعُ الجسم، الحجم، الإصدار، الجهازُ من القائمة، والقيمُ في مجالها.

    قيمةٌ مفقودةٌ (`null`) مقبولةٌ (صفحةٌ بلا تفاعلٍ لا INP لها)، وقيمةٌ خارجَ المجال ترفض الحمولةَ كلَّها (مقياسٌ فاسدٌ أو عبث).
    ولا شيءَ من الحمولة إلّا الجهازُ والمقاييسُ الثلاثة يخرج من هذه الدالّة.
    """
    if not raw or len(raw) > MAX_BODY_BYTES:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict) or data.get("v") != 1 or data.get("dev") not in DEVICES:
        return None
    for key, allowed in (("lay", LAYOUTS), ("nav", NAV), ("net", NET)):
        if data.get(key) is not None and data.get(key) not in allowed:
            return None
    values: dict[str, float | None] = {}
    for key, metric in METRICS.items():
        raw_value = data.get(key)
        if raw_value is None:
            values[key] = None
            continue
        value = _number(raw_value, 0, metric.maximum)
        if value is None:
            return None
        values[key] = value
    if all(value is None for value in values.values()):
        return None
    return {"dev": data["dev"], **values}


def _day(moment: float) -> int:
    return int(moment // 86400)


def _bucket_key(day: int, device: str, metric: str, bucket: int) -> str:
    return f"qcc:rum:{day}:{device}:{metric}:{bucket}"


def _throttled(moment: float) -> bool:
    key = f"qcc:rum:rate:{int(moment // 60)}"
    cache.add(key, 0, 120)
    try:
        return int(cache.incr(key)) > RATE_PER_MINUTE
    except ValueError:
        return False


def record(payload: dict[str, Any], now: float | None = None) -> bool:
    """يزيد عدّاداتِ دلاء اليوم — يعيد هل سُجّلت. لا يرفع أبداً (العطلُ يُرمى صامتاً)."""
    moment = time.time() if now is None else now
    try:
        if _throttled(moment):
            return False
        day = _day(moment)
        for key, metric in METRICS.items():
            value = payload.get(key)
            if value is None:
                continue
            bucket_key = _bucket_key(day, payload["dev"], key, metric.bucket(value))
            cache.add(bucket_key, 0, _TTL)
            cache.incr(bucket_key)
        return True
    except Exception:  # noqa: BLE001 — القياسُ تابعٌ: لا يُسقط طلباً ولا يكشف شيئاً
        logger.debug("rum: could not record", exc_info=True)
        return False


def summary(
    device: str, days: int = 7, now: float | None = None
) -> dict[str, dict[str, float | int | None]]:
    """{مقياس: {n، p75}} لجهازٍ على آخر `days` أيّام (اليومَ وما قبله). `p75` هو الحدُّ الأعلى للدلو، أو None عند غياب العيّنة."""
    moment = time.time() if now is None else now
    today = _day(moment)
    out: dict[str, dict[str, float | int | None]] = {}
    for key, metric in METRICS.items():
        keys = [
            _bucket_key(today - back, device, key, bucket)
            for back in range(days)
            for bucket in range(metric.count + 1)
        ]
        found = cache.get_many(keys)
        totals = [0] * (metric.count + 1)
        for cache_key, value in found.items():
            totals[int(cache_key.rsplit(":", 1)[1])] += int(value)
        n = sum(totals)
        p75 = None
        if n:
            target, running = 0.75 * n, 0
            for bucket, count in enumerate(totals):
                running += count
                if running >= target:
                    p75 = metric.upper(bucket)
                    break
        out[key] = {"n": n, "p75": p75}
    return out


def rating(key: str, p75: float | None, n: int) -> str:
    """good / needs / poor / none — `poor` لا يُعلَن دون عيّنةٍ كافية (`BAD_SAMPLE`)، و`none` دون الحدّ الأدنى."""
    if p75 is None or n < MIN_SAMPLE:
        return "none"
    metric = METRICS[key]
    if p75 <= metric.good:
        return "good"
    return "poor" if p75 > metric.poor and n >= BAD_SAMPLE else "needs"
