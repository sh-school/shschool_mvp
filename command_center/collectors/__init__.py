"""مجمِّعاتُ «مركز قيادة الجودة» — تكتب لوحاتِ اللقطة في الـcache (عقدُ `command_center/contract.py`).

الصفحةُ لا تحسب شيئاً عند الرسم؛ هذه الحزمةُ تحسب في الخلفيّة وتكتب المغلَّفَ. قسمان بحسب المصدر:

- **محلّيّة** (`LOCAL`): قاعدةُ البيانات والـcache والملفّاتُ المشحونة — سريعةٌ ولا شبكةَ فيها؛ تُجمَع كلَّ دقيقة.
- **GitHub** (`REMOTE`): واجهةُ GitHub العامّةُ بلا رمز (الحدُّ 60 طلباً في الساعة) بطلباتٍ شرطيّة (ETag)؛ تُجمَع كلَّ أربع دقائق (`shschool/celery.py:qcc-collect-remote`).

كلُّ مجمِّعٍ يعزل عطلَه: يكتب `ok=False` برمزٍ ثابتٍ فتبقى آخرُ قيمةٍ سليمةٍ وتُعرض تحذيراً، ولا يُسقط غيرَه.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from command_center import alerts, webstats
from command_center.collectors import (
    ci,
    compliance,
    database,
    delivery,
    guards,
    messaging,
    production,
    pulls,
    quality,
    roadmap,
    security,
    supply,
    ux,
)

logger = logging.getLogger(__name__)

Collector = Callable[[], None]

#: لوحةٌ ← مجمِّعُها. أسماءُ اللوحات في `contract.PANELS`، واختبارٌ يحرس تطابقَ القائمتين.
LOCAL: dict[str, Collector] = {
    "production": production.collect,
    "database": database.collect,
    "compliance": compliance.collect,
    "messaging": messaging.collect,
    "security": security.collect,
    "ux": ux.collect,
    "guards": guards.collect,
    "roadmap": roadmap.collect,
}
REMOTE: dict[str, Collector] = {
    "ci": ci.collect,
    "pulls": pulls.collect,
    "supply": supply.collect,
    "quality": quality.collect,
    "delivery": delivery.collect,
}
#: لوحاتٌ تقرؤها **عمليّةُ الويب** لا العامل (مقاييسُ في ذاكرتها) — تُؤخذ عيّنتُها عند فتح الصفحة أو استطلاعها (`webstats.sample_safe`).
WEB: dict[str, Collector] = {"latency": webstats.sample}


def run(collectors: dict[str, Collector]) -> dict[str, bool]:
    """يشغّل المجمِّعاتِ واحداً واحداً — نتيجةُ كلٍّ منها نجاحٌ أو فشلٌ، ولا استثناءَ يتسرّب."""
    outcome: dict[str, bool] = {}
    for panel, collect in collectors.items():
        try:
            collect()
            outcome[panel] = True
        except Exception:  # noqa: BLE001 — مجمِّعٌ معطوبٌ لا يوقف اللوحاتِ الأخرى
            logger.exception("command center: collector %s failed", panel)
            outcome[panel] = False
    alerts.safe_evaluate()  # التنبيهُ الحيّ عند الأحمر بعد كلّ دورة جمع (command_center/alerts.py)
    return outcome
