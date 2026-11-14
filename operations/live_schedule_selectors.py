"""live_schedule_selectors.py —بطاقةُ «الجدول الحيّ» في صفحة الجدولة الذكية.

تقرأ التوليدَ المعتمَدَ وحصصَه الحيّة وتقيّمها بالمُقيِّم المستقلّ، ثمّ تفصل ما يُقرأ تعارضاً فعلياً
عمّا هو قاعدةُ توزيعٍ يتبعها المولّد ولا يتبعها المصدرُ المستورَد (aSc). للقراءة وحدَها: لا تكتب
في ScheduleSlot ولا تغيّر حالةَ أيّ توليد، ولا تمسّ حكمَ المُقيِّم على المسودّات.
"""

from __future__ import annotations

from typing import Any

from .models import ScheduleGeneration, ScheduleSlot
from .schedule_evaluator import evaluate_slots, live_slots

#: ما يُعدّ تعارضاً فعلياً: تداخلُ الشعبة/المعلّم (HC1 وHC2 وHC12 وHC9) وحصّةٌ في خانة تفريغ (EX).
ACTUAL_CODES = ("HC1", "HC2", "HC12", "HC9", "EX")
IMPORT_MODE = "import"

_DAY_NAMES = dict(ScheduleSlot.DAYS)


def _row(breach: Any) -> dict[str, Any]:
    """صفُّ تعارضٍ للعرض: القيد والشعبة والمادّة والمعلّم واليوم والحصّة."""
    return {
        "code": breach.code,
        "class_name": breach.class_name,
        "subject_name": breach.subject_name,
        "teacher_name": breach.teacher_name,
        "day": _DAY_NAMES.get(breach.day, str(breach.day)),
        "period": breach.period,
    }


def live_schedule_card(school: Any, year: str) -> dict[str, Any] | None:
    """بطاقةُ التوليد المعتمَد للعام، أو None إن لم يوجد توليدٌ معتمَد."""
    generation = (
        ScheduleGeneration.objects.filter(school=school, academic_year=year, status="approved")
        .order_by("-generated_at")
        .first()
    )
    if generation is None:
        return None
    imported = (generation.config_snapshot or {}).get("mode") == IMPORT_MODE
    slots = list(live_slots(school, year))
    ev = evaluate_slots(school, year, slots)

    actual = [_row(b) for b in ev.breach_rows if b.code in ACTUAL_CODES]
    notes: dict[str, int] = {}
    for b in ev.breach_rows:
        if b.code not in ACTUAL_CODES:
            notes[b.code] = notes.get(b.code, 0) + 1
    # المزدوجةُ غيرُ المتّصلة بالجرس موجودةٌ فعلاً: تُحسب في الاكتمال للمستورَد وتُعرض ملاحظةً.
    unjoined = ev.unjoined_periods if imported else 0
    placed = ev.placed_periods + unjoined
    required = ev.required_periods
    return {
        "generation": generation,
        "imported": imported,
        "slots_count": len(slots),
        "approved_on": generation.generated_at,
        "actual": actual,
        "actual_count": len(actual),
        "notes": sorted(notes.items()),
        "notes_count": sum(notes.values()),
        "unjoined_periods": unjoined,
        "placed": placed,
        "required": required,
        "completeness": round(100 * placed / required, 1) if required else 100,
    }
