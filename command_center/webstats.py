"""لوحةُ «الأداء والأخطاء (الويب)» — p95 لزمن الاستجابة ونسبةُ 5xx من مقاييس `django_prometheus` في **عمليّة الويب نفسِها**.

المقاييسُ (`django_http_requests_latency_seconds_by_view_method` و`django_http_responses_total_by_status`) تعيش في ذاكرة عمليّة الويب، والعاملُ (Celery) لا يراها؛
فهذه اللوحةُ **الوحيدةُ التي يقرؤها الويبُ لا العامل**: تُؤخذ عيّنةٌ عند فتح الصفحة أو استطلاعِ اللقطة (مرّةً كلَّ 30 ثانيةً بقفلٍ في الـcache) — قراءةُ سجلٍّ في الذاكرة بلا شبكةٍ ولا استعلام.
**حدودُها** (تُقرأ قبل تفسير الأرقام): الأرقامُ **منذ آخر إعادة تشغيلٍ للعمليّة** لا نافذةٌ متحرّكة؛ وعمليّاتُ ويبٍ متعدّدةٌ لكلٍّ سجلُّها فتُعرض عمليّةُ آخر من قرأ؛
ولا تتحدّث ما لم يفتح أحدٌ الصفحةَ (فتصير قديمةً «انتبه» لا سليمة، والتنبيهُ الآليُّ لا يعتمد عليها).
- **زمنُ الاستجابة p95** (الحدُّ الأعلى للدلو): «انتبه» فوق ثانيتين وأحمرُ فوق خمس.
- **نسبةُ 5xx**: «انتبه» من 1% وأحمرُ من 5%.
- **عيّنةٌ دون 200 طلب**: بلا حكم («انتبه» بعنوانٍ صريح). لا مسارَ ولا اسمَ عرضٍ يُخزَّن — أعدادٌ فقط.
"""

from __future__ import annotations

import logging
import time

from django.conf import settings
from django.core.cache import cache

from command_center import contract
from command_center.collectors.publish import publish, score, worst

logger = logging.getLogger(__name__)

PANEL = "latency"
LATENCY_FAMILY = "django_http_requests_latency_seconds_by_view_method"
STATUS_FAMILY = "django_http_responses_total_by_status"
LOCK_KEY = "qcc:web:sample"
LOCK_SECONDS = 30
MIN_REQUESTS = 200
P95_WARN, P95_BAD = 2.0, 5.0
ERR_WARN, ERR_BAD = 0.01, 0.05


def read_registry() -> tuple[dict[float, float], int, int]:
    """(دلاءٌ تراكميّةٌ {الحدّ: العدد}، مجموعُ الطلبات، طلباتُ 5xx) من سجلّ العمليّة."""
    from prometheus_client import REGISTRY

    buckets: dict[float, float] = {}
    total = errors = 0
    for family in REGISTRY.collect():
        if family.name == LATENCY_FAMILY:
            for sample in family.samples:
                if sample.name.endswith("_bucket"):
                    edge = float(sample.labels["le"])
                    buckets[edge] = buckets.get(edge, 0) + sample.value
        elif family.name == STATUS_FAMILY:
            for sample in family.samples:
                if sample.name.endswith("_total"):
                    total += int(sample.value)
                    if str(sample.labels.get("status", "")).startswith("5"):
                        errors += int(sample.value)
    return buckets, total, errors


def p95(buckets: dict[float, float]) -> float | None:
    """الحدُّ الأعلى للدلو الذي يحوي المئينَ 95 — None دون طلبات؛ و`inf` يُعاد كما هو (أبطأُ من آخر دلوٍ محدود)."""
    if not buckets:
        return None
    edges = sorted(buckets)
    count = buckets[edges[-1]]
    if not count:
        return None
    target = 0.95 * count
    for edge in edges:
        if buckets[edge] >= target:
            return edge
    return edges[-1]


def levels(p95_seconds: float | None, total: int, errors: int) -> list[str]:
    if total < MIN_REQUESTS or p95_seconds is None:
        return [contract.WARN]
    share = errors / total
    latency = (
        contract.BAD
        if p95_seconds > P95_BAD
        else (contract.WARN if p95_seconds > P95_WARN else contract.OK)
    )
    errs = (
        contract.BAD if share >= ERR_BAD else (contract.WARN if share >= ERR_WARN else contract.OK)
    )
    return [latency, errs]


def sample() -> None:
    buckets, total, errors = read_registry()
    value = p95(buckets)
    found = levels(value, total, errors)
    thin = total < MIN_REQUESTS or value is None
    if thin:
        headline = f"عيّنةٌ قليلةٌ ({total} من {MIN_REQUESTS} طلباً منذ إعادة التشغيل)"
    elif worst(found) == contract.OK:
        headline = "الاستجابةُ سريعةٌ والأخطاءُ نادرة"
    else:
        headline = "الأداءُ بحاجةٍ إلى نظر"
    shown = "—" if value is None else ("> أبطأُ دلو" if value == float("inf") else f"{value:g} ث")
    publish(
        PANEL,
        status=contract.WARN if thin else worst(found),
        headline=headline,
        gauge=None if thin else score(found),
        detail="منذ آخر إعادة تشغيلٍ لعمليّة الويب هذه",
        metrics=(
            ("زمنُ الاستجابة p95", shown),
            ("طلباتٌ منذ التشغيل", total),
            ("استجاباتُ 5xx", f"{errors} ({100 * errors / total:.1f}%)" if total else "0"),
        ),
    )


def sample_safe(now: float | None = None) -> bool:
    """عيّنةٌ مقفولةٌ 30 ثانيةً ولا ترفع أبداً — تُستدعى من عرضَي الصفحة واللقطة.

    يحكمها `QCC_LAZY_REFRESH` نفسُه (الجمعُ الذاتيُّ عند القراءة): مطفأٌ في الاختبارات فلا تتلوّث لوحاتٌ يُفترض أنّها لم تُجمَع.
    """
    if not getattr(settings, "QCC_LAZY_REFRESH", True):
        return False
    moment = time.time() if now is None else now
    try:
        if not cache.add(LOCK_KEY, moment, LOCK_SECONDS):
            return False
        sample()
        return True
    except Exception:  # noqa: BLE001 — القياسُ تابعٌ: لا يُسقط الصفحة
        logger.warning("command center: web sample failed", exc_info=True)
        return False
