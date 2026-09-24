"""operations/schedule_breaches.py — مخالفاتُ المسودّة عند اعتمادها (SCH-05).

المدقّقُ (`scheduler_audit`) يكتب في لقطة التوليد ما بقي مكسوراً بعد السداد:
`{"count", "by_code", "items": [{code, class, subject, teacher, day, period}]}`.
وقد اعتُمد جدولُ 2026-09-24 وفيه اثنتا عشرةَ مخالفةً لـHC6 لم يرها من اعتمده —
فالمختبرُ يلخّصها في «98.2% مطابقة»، لا شعبةً ومادّةً ويوماً.

فهنا تُقرأ المخالفاتُ كما تُعرض — مجموعةً برمز قيدها وعنوانه من السجلّ — ويُحكم
أتُعتمد المسودّةُ بلا إقرار. ولا استعلامَ هنا: اللقطةُ على الصفّ المقروء أصلاً.
والتوليدُ الأقدمُ من المدقّق لا لقطةَ فيه، فلا يُعرض له شيءٌ ولا يُحجب اعتمادُه:
غيابُ الشهادة ليس شهادةً بالمخالفة.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.dashboard_presentation import chunk_for_grid

from .constraint_registry import REGISTRY
from .models import ScheduleGeneration, ScheduleSlot
from .scheduler_audit import EXEMPTION

#: حقلُ الإقرار في نموذج الاعتماد (`templates/schedule/smart_schedule.html`).
ACKNOWLEDGE_FIELD = "acknowledge_breaches"

_DAY_NAMES = dict(ScheduleSlot.DAYS)
#: السطرُ شعبةٌ ومادّةٌ ومعلّمٌ ويوم — ضيّقٌ وعددُه بلا سقف (تسعٌ وستّون في نسخة
#: الإنتاج)، فيُقسَّم أعمدةً متجاورةً لا عموداً يطيل الصفحة (معيار تخطيط الصفحات).
_COLUMNS = 3
#: المجموعاتُ بترتيب السجلّ (HC1..HC20)، والتفريغُ وما لا يُعرف بعدها.
_ORDER = {code: index for index, code in enumerate(REGISTRY)}


def _title(code: str) -> str:
    if code == EXEMPTION:
        return "تفريغ معلّم"
    spec = REGISTRY.get(code)
    return spec.title if spec else code


def draft_breaches(snapshot: dict | None) -> dict | None:
    """`{count, groups: [{code, title, count, cols}]}` — أو `None` لتوليدٍ سبق المدقّق."""
    recorded = (snapshot or {}).get("breaches")
    if not isinstance(recorded, dict):
        return None
    grouped: dict[str, list[dict]] = {}
    for item in recorded.get("items") or []:
        row = {**item, "day_name": _DAY_NAMES.get(item.get("day"), "")}
        grouped.setdefault(str(item.get("code") or ""), []).append(row)
    groups = [
        {
            "code": code,
            "title": _title(code),
            "count": len(rows),
            "cols": chunk_for_grid(rows, _COLUMNS),
        }
        for code, rows in sorted(grouped.items(), key=lambda pair: _ORDER.get(pair[0], len(_ORDER)))
    ]
    return {"count": int(recorded.get("count") or 0), "groups": groups}


class BreachesNotAcknowledgedError(Exception):
    """اعتمادُ مسودّةٍ فيها مخالفاتٌ صلبةٌ لم يُقَرّ بها — السببُ يُقال كما هو."""


def acknowledged(data: Mapping[str, Any]) -> bool:
    """أأقرّ الطلبُ بالمخالفات؟ — حقلُ النموذج بقيمته الصريحة."""
    return data.get(ACKNOWLEDGE_FIELD) == "1"


def approval_refusal(gen: ScheduleGeneration, acknowledged_: bool) -> str:
    """سببُ رفض الاعتماد — أو نصٌّ فارغٌ إن جاز.

    القيدُ الصلبُ لا يُكسر بصمت: إمّا يُسدَّد قبل انتهاء التوليد، وإمّا يُعلَن
    بموضعه ويُقرّ به من يعتمد. والإقرارُ حقلٌ في الطلب يُحكم فيه على الخادم، لا
    تأكيدُ المتصفّح وحدَه — ذاك يتجاوزه طلبٌ مباشر.
    """
    breaches = draft_breaches(gen.config_snapshot)
    count = breaches["count"] if breaches else 0
    if not count or acknowledged_:
        return ""
    return (
        f"لم يُعتمد الجدول: في المسودّة مخالفاتٌ لقيودٍ صلبة (عددُها {count}). "
        "راجعها في سجلّ التوليد، ثمّ أقرَّ بها صراحةً عند الاعتماد."
    )
