"""عدّادُ أخطاء الخادم (5xx) لبطاقة «أخطاء الخادم» في رئيسيّة الإدارة (OWN-23).

Sentry يلتقط الأخطاء لكنّ قراءةَ أرقامه من داخل المنصّة تحتاج مفتاحَ API وطلباً خارجيّاً عند رسم الصفحة،
وحصّتُه المجّانيّةُ استُنفدت أصلاً (2026-09-21). فالعدّادُ ذاتيٌّ في الـcache (Redis في الإنتاج) بنمط
`worker_heartbeat`: لا جدولَ جديد ولا RLS ولا وثيقةَ احتفاظ، والويبُ والعاملُ يشتركان في Redis نفسه.

يُخزَّن ما يكفي المطوّرَ ليعرف أين ينظر — عددٌ في كلّ ساعة، وآخرُ خطأٍ (نمطُ المسار واسمُ صنف الاستثناء) —
ولا يُخزَّن نصُّ الاستثناء ولا الرابطُ الخام ولا هويّةُ أحد: أنماطُ المسارات (`students/<uuid:pk>/`) لا قيمُها،
وأسماءُ الأصناف لا رسائلُها (PDPPL). سقوطُ الـcache يُفقد العدَّ ولا يُسقط طلباً: كلُّ استدعاءٍ هنا يبتلع عطلَه.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from django.core.cache import cache

logger = logging.getLogger(__name__)

BUCKET_SECONDS = 3600
#: ساعتان وأربعون: يكفي مقارنةَ 24 ساعةً بالأربع والعشرين قبلها ثمّ يزول.
_BUCKET_TTL = 49 * 3600
_LAST_KEY = "err5xx:last"
#: أسبوع: آخرُ خطأٍ يبقى مقروءاً (قديماً) ولو خلا يومٌ كاملٌ من الأخطاء.
_LAST_TTL = 7 * 24 * 3600
_MAX_ROUTE = 120


def _bucket_key(hour: int) -> str:
    return f"err5xx:{hour}"


def record(route: str, exc_class: str = "", now: float | None = None) -> None:
    """يزيد عدّاد الساعة الجارية ويحفظ آخرَ خطأ. لا يرفع أبداً."""
    try:
        moment = time.time() if now is None else now
        key = _bucket_key(int(moment // BUCKET_SECONDS))
        cache.add(key, 0, _BUCKET_TTL)
        try:
            cache.incr(key)
        except ValueError:  # انتهى مفتاحُ الساعة بين add وincr
            cache.set(key, 1, _BUCKET_TTL)
        cache.set(
            _LAST_KEY,
            {"at": moment, "route": route[:_MAX_ROUTE], "exc": exc_class[:80]},
            _LAST_TTL,
        )
    except Exception:  # noqa: BLE001 — العدُّ تابعٌ للطلب: لا يُسقطه أيُّ عطلٍ في الـcache
        logger.debug("5xx counter unavailable", exc_info=True)


def counts(now: float | None = None) -> tuple[int, int]:
    """(أخطاءُ آخر 24 ساعة، أخطاءُ الأربع والعشرين قبلها) — بالساعات المكتملة والجارية."""
    moment = time.time() if now is None else now
    current = int(moment // BUCKET_SECONDS)
    recent = [_bucket_key(current - offset) for offset in range(24)]
    earlier = [_bucket_key(current - offset) for offset in range(24, 48)]
    stored: dict[str, Any] = cache.get_many(recent + earlier)
    return (
        sum(int(stored.get(key, 0)) for key in recent),
        sum(int(stored.get(key, 0)) for key in earlier),
    )


def last_error() -> dict[str, Any] | None:
    """آخرُ خطأٍ مسجَّل: {"at": ثوانٍ، "route": نمطُ المسار، "exc": صنفُ الاستثناء} أو None."""
    value = cache.get(_LAST_KEY)
    return value if isinstance(value, dict) else None
