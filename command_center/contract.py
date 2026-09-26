"""عقدُ اللقطة v1 — ما تكتبه المجمِّعاتُ في الـcache وما تقرؤه الصفحةُ منه.

«مركز قيادة الجودة» صفحةٌ في المنصّة للمطوّر وحدَه في `/command-center/`: عرضٌ حيٌّ لصحّة المنصّة. والصفحةُ **لا تحسب
شيئاً عند الرسم**: تقرأ الـcache وحدَه (≤ 50ms، بلا شبكةٍ ولا استعلامٍ ثقيل). وما فوق 300ms مجمِّعٌ في مهمّة Celery
يكتب مغلَّفاً `{data, fetched_at, ok, err}` في مفتاح لوحته بنمط `core/backup_status.py`:

- `data`: أرقامٌ وتصنيفاتٌ فقط — المستودعُ **عامّ**، فلا نصَّ من طرفٍ ثالثٍ (عنوانُ طلبٍ مثلاً) ولا رقمٌ شخصيّ.
  وفيه `status` (`ok` أو `warn` أو `bad`) و`headline` (جملةٌ قصيرةٌ من ثوابتَ يكتبها المجمِّعُ) و`detail` اختياريّ،
  و`gauge` اختياريٌّ (0–100: قراءةُ القرص الدائريّ، والمئةُ أسلم) وحتّى أربعةِ مؤشّراتٍ ثانويّةٍ `m1_l`/`m1_v` … `m4_l`/`m4_v`
  (عنوانٌ وقيمةٌ قصيران). وكلُّها إضافةٌ لا تكسر العقد: لوحةٌ بلا `gauge` تُرسم بقرصٍ فارغ.
- `fetched_at`: زمنُ آخرِ جلبٍ ناجح — والقِدَمُ يُحكم منه لا من انتهاء مفتاح الـcache.
- `ok`: نجاحُ آخر محاولة؛ فإن فشلت بقيت آخرُ قيمةٍ سليمةٍ ويُعلَّم `ok=False` فتظهر «تحذيراً» لا «سليماً».
- `err`: رمزُ العطل (ثابتٌ قصير) لا نصُّ الاستثناء.

الحالةُ **«غيرُ معلوم» ليست خضراء**: لوحةٌ بلا مغلَّفٍ (لم يُجمَع بعدُ) أو بلا `status` مفهوم تُعرض `unknown`،
والمقصودُ ألّا يُقرأ الغيابُ سلامةً. وهذا الملفُّ هو المرجعُ الوحيد لأسماء اللوحات وحدودِ القِدَم.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from django.core.cache import cache

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

UNKNOWN, OK, WARN, BAD = "unknown", "ok", "warn", "bad"
STATUSES = (OK, WARN, BAD)

CACHE_PREFIX = "qcc:panel:"
#: أسبوع: القيمةُ تبقى مقروءةً (قديمةً) ولو انقطع الجمعُ بدل أن تختفي فتُقرأ «غيرَ معلومة».
TTL_SECONDS = 7 * 24 * 3600
#: القِدَمُ بمضاعف دورة تحديث اللوحة: بعد هذا الحدّ لا تُعرض «سليمةً» ولو كانت آخرُ قيمةٍ سليمة.
STALE_AFTER_REFRESHES = 6
MAX_STRING = 120
MAX_METRICS = 4


@dataclass(frozen=True)
class Panel:
    key: str
    title: str
    #: ثوانٍ بين استطلاعَين في الصفحة (15–60 بحسب اللوحة).
    refresh: int


PANELS: tuple[Panel, ...] = (
    Panel("production", "صحّةُ الإنتاج والنشر", 30),
    Panel("ci", "فحوصُ CI", 60),
    Panel("guards", "الحرّاسُ والميزانيّات", 60),
    Panel("roadmap", "الخارطةُ وقراراتُك", 60),
    Panel("pulls", "الطلباتُ ومسارُ الدمج", 60),
)


def _gauge_of(data: dict[str, Any]) -> int | None:
    """قراءةُ القرص 0–100 أو None إن غابت أو لم تكن عدداً — تُقصّ إلى المدى ولا تُرفع."""
    value = data.get("gauge")
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return max(0, min(100, round(value)))


def _metrics_of(data: dict[str, Any]) -> list[dict[str, str]]:
    """المؤشّراتُ الثانويّةُ الموجودةُ فقط بترتيبها: [{label, value}] — عنوانٌ وقيمةٌ نصّان."""
    found = []
    for index in range(1, MAX_METRICS + 1):
        label, value = data.get(f"m{index}_l"), data.get(f"m{index}_v")
        if label in (None, "") or value is None:
            continue
        found.append({"label": str(label), "value": str(value)})
    return found


def cache_key(panel_key: str) -> str:
    return f"{CACHE_PREFIX}{panel_key}"


def _scalar(value: Any) -> bool:
    return (
        value is None
        or isinstance(value, bool | int | float)
        or (isinstance(value, str) and len(value) <= MAX_STRING)
    )


def valid_data(data: Any) -> bool:
    """أرقامٌ وتصنيفاتٌ وجملٌ قصيرة: قاموسٌ مسطَّحٌ مفاتيحُه نصوصٌ وقيمُه أعدادٌ أو نصوصٌ قصيرة."""
    return (
        isinstance(data, dict)
        and all(isinstance(k, str) for k in data)
        and all(_scalar(v) for v in data.values())
    )


def store(panel_key: str, data: dict[str, Any], *, ok: bool = True, err: str = "") -> None:
    """كتابةُ مجمِّعٍ للمغلَّف — الطريقُ الوحيد لوضع قيمةٍ في لوحة. يرفض الشكلَ غيرَ المسطَّح والنصَّ الطويل.

    عند `ok=False` تُحفظ `data` الأخيرةُ السليمةُ كما هي (لا تُستبدل بفارغٍ) ويُحدَّث الرمزُ وحدَه.
    """
    if panel_key not in {p.key for p in PANELS}:
        raise ValueError(f"لوحةٌ غيرُ معروفة: {panel_key}")
    if not valid_data(data):
        raise ValueError("data يجب أن تكون قاموساً مسطَّحاً من أعدادٍ ونصوصٍ قصيرة")
    previous = cache.get(cache_key(panel_key))
    if not ok and isinstance(previous, dict) and isinstance(previous.get("data"), dict):
        envelope = {**previous, "ok": False, "err": str(err)[:40]}
    else:
        envelope = {
            "data": data,
            "fetched_at": time.time(),
            "ok": bool(ok),
            "err": "" if ok else str(err)[:40],
        }
    cache.set(cache_key(panel_key), envelope, TTL_SECONDS)


def _status_of(envelope: Any, refresh: int, now: float) -> tuple[str, float | None, dict[str, Any]]:
    """(الحالة، العمرُ بالثواني، data) — أيُّ شكلٍ غيرِ مفهوم = unknown."""
    if not isinstance(envelope, dict) or not valid_data(envelope.get("data")):
        return UNKNOWN, None, {}
    data = envelope["data"]
    fetched = envelope.get("fetched_at")
    age = max(0.0, now - fetched) if isinstance(fetched, int | float) else None
    status = data.get("status")
    if status not in STATUSES or age is None:
        return UNKNOWN, age, data
    stale = age > refresh * STALE_AFTER_REFRESHES
    if status == OK and (stale or not envelope.get("ok", True)):
        status = WARN
    return str(status), age, data


def read_panels(now: float | None = None) -> list[dict[str, Any]]:
    """لوحاتُ اللقطة بترتيب `PANELS` — قراءةُ cache واحدةٌ، ولا يسقط الرسمُ إن تعطّل الـcache."""
    moment = time.time() if now is None else now
    try:
        found = cache.get_many([cache_key(p.key) for p in PANELS])
    except Exception:  # الـcache خارجيّ: عطلُه يعرض «غير معلوم» ولا يُسقط الصفحة
        logger.warning("command center: cache unreadable", exc_info=True)
        found = {}
    panels = []
    for panel in PANELS:
        envelope = found.get(cache_key(panel.key))
        status, age, data = _status_of(envelope, panel.refresh, moment)
        panels.append(
            {
                "key": panel.key,
                "title": panel.title,
                "refresh": panel.refresh,
                "status": status,
                "age_seconds": None if age is None else int(age),
                "ok": bool(envelope.get("ok", True)) if isinstance(envelope, dict) else None,
                "err": str(envelope.get("err", ""))[:40] if isinstance(envelope, dict) else "",
                "headline": str(data.get("headline", "")),
                "detail": str(data.get("detail", "")),
                "gauge": _gauge_of(data),
                "metrics": _metrics_of(data),
            }
        )
    return panels


def snapshot(now: float | None = None) -> dict[str, Any]:
    """اللقطةُ v1: ما تُرجعه `/command-center/snapshot/` وما ترسمه الصفحةُ عند أوّل تحميل."""
    moment = time.time() if now is None else now
    return {"schema": SCHEMA_VERSION, "generated_at": int(moment), "panels": read_panels(moment)}
