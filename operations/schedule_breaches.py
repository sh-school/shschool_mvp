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


def budget_cut_notice(snapshot: dict | None) -> dict | None:
    """`{attempt, after_seconds}` إن قُطع إصلاحُ التوليد بنفاد الميزانية — وإلّا `None`.

    فالمتعذّراتُ حينها قد تكون من قطعٍ لا من استحالة، ومن يعتمد المسودّةَ يُخبَر بذلك (0105، W-20261002-033).
    """
    recorded = snapshot or {}
    if not recorded.get("budget_cut"):
        return None
    return {
        "attempt": recorded.get("budget_cut_attempt"),
        "after_seconds": recorded.get("budget_cut_after_s"),
    }


class BreachesNotAcknowledgedError(Exception):
    """اعتمادُ مسودّةٍ فيها مخالفاتٌ صلبةٌ لم يُقَرّ بها — السببُ يُقال كما هو."""


def acknowledged(data: Mapping[str, Any]) -> bool:
    """أأقرّ الطلبُ بالمخالفات؟ — حقلُ النموذج بقيمته الصريحة."""
    return data.get(ACKNOWLEDGE_FIELD) == "1"


def unplaced_count(snapshot: dict | None) -> int:
    """عددُ المهامّ التي لم تجد موضعاً في المسودّة (`config_snapshot["unplaced"]`) — وصفرٌ للقطةٍ أقدم لا تحمله."""
    recorded = (snapshot or {}).get("unplaced")
    if isinstance(recorded, int) and not isinstance(recorded, bool) and recorded > 0:
        return recorded
    return 0


def quality_display(relative: float | None, unplaced: int, breaches: int) -> dict:
    """درجةُ عمود «الجودة» في سجلّ التوليد — **الصحّةُ أوّلاً ثمّ الجودة** (W-20261003-010).

    الدرجةُ المنسوبةُ متوسّطُ نِسَب المؤشّرات إلى أساسها، وكلٌّ منها حتى 120 — فـ«اكتمالُ النصاب»
    واحدٌ من اثنين وعشرين يُمحى أثرُه بتحسّنٍ في غيره، ومخالفاتُ المدقّق (HC14، HC16B…) ليست في
    المختبر أصلاً. فأُعلنت مسودّةٌ فيها ثلاثُ متعذّراتٍ وخمسُ مخالفاتٍ «100%» فوق جدولين كاملين «99%»:
    حذفُ ما يصعب وضعُه يُريح المؤشّراتِ المرنة فيرفع الرقم.

    والمولّدُ نفسُه يفاضل معجميّاً (المتعذّراتُ قبل الدرجة، `scheduler.py`)، والمقارنةُ بالدرجة لا
    تصحّ إلّا بين جدولين متساويَين صحّةً (ADR-0008 §5). فالمسودّةُ الناقصةُ أو المكسورةُ لا تُعطى
    درجةً تُقارَن: تُوسَم «ناقصة» بلون الخطر، وتُذكر درجةُ ما وُضع فيها ثانويّةً مسمّاةً باسمها،
    وتُفرَز تحت كلِّ جدولٍ سليم.
    """
    invalid = bool(unplaced or breaches)
    if relative is None:
        return {"invalid": invalid, "value": None, "tone": "danger" if invalid else "", "sort": ""}
    return {
        "invalid": invalid,
        "value": relative,
        "tone": "danger" if invalid else "",
        # الفرزُ معجميّ: كلُّ سليمٍ فوق كلِّ ناقص، ثمّ بالدرجة داخل كلٍّ منهما.
        "sort": round(relative - (1000 if invalid else 0), 1),
    }


def approval_refusal(gen: ScheduleGeneration, acknowledged_: bool) -> str:
    """سببُ رفض الاعتماد — أو نصٌّ فارغٌ إن جاز.

    القيدُ الصلبُ لا يُكسر بصمت: إمّا يُسدَّد قبل انتهاء التوليد، وإمّا يُعلَن
    بموضعه ويُقرّ به من يعتمد. والإقرارُ حقلٌ في الطلب يُحكم فيه على الخادم، لا
    تأكيدُ المتصفّح وحدَه — ذاك يتجاوزه طلبٌ مباشر.

    وكذلك **المتعذّرات** (OR-01، قرارُ المالك): جدولٌ فيه حصّةٌ لم تجد موضعاً لا يُعتمد إلّا بإقرارٍ صريحٍ
    مسجَّل — فكان يُعتمد بضغطةٍ واحدةٍ لأنّ الحارسَ لا يعدّ إلّا المخالفاتِ المُسنَدةَ لقيودٍ صلبة. وإن قُطع البحثُ
    بنفاد الميزانية يُذكر ذلك: المتعذّرُ حينها قد يكون من قطعٍ لا من استحالة.
    """
    breaches = draft_breaches(gen.config_snapshot)
    count = breaches["count"] if breaches else 0
    unplaced = unplaced_count(gen.config_snapshot)
    if (not count and not unplaced) or acknowledged_:
        return ""
    parts = []
    if count:
        parts.append(f"مخالفاتٌ لقيودٍ صلبة (عددُها {count})")
    if unplaced:
        parts.append(f"{unplaced} مهمّةً متعذّرةً لم تجد موضعاً")
    message = (
        f"لم يُعتمد الجدول: في المسودّة {' و'.join(parts)}. "
        "راجعها في سجلّ التوليد، ثمّ أقرَّ بها صراحةً عند الاعتماد."
    )
    if unplaced and budget_cut_notice(gen.config_snapshot):
        message += " وقد قُطع البحثُ بنفاد الميزانية فقد تُحلّ المتعذّراتُ بميزانيةٍ أطول."
    return message
