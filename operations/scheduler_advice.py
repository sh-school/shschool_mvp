"""نصائحُ وتشخيصُ سعة المعلّمين لمتعذّرات التوليد — بالحساب لا بالتخمين."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .scheduler import Task


def _slack_advice(
    leftovers: list[Task], prefs: Any, blocked_slots: set, tasks: list[Task]
) -> list[str]:
    """متعذّرةٌ لمعلّمٍ سعتُه تساوي نصابَه: يُقال له أين الهامشُ لا «تعذّر» وحدَها.

    سفيان (2026-09-04): تفريغاتٌ تترك له اثنتي عشرةَ خانةً بلا تلاصق لاثنتي عشرةَ
    حصّة — فأيُّ قيدٍ آخر (تنوّعُ الحصّة، القسمة، شعبةٌ بلا خانةٍ فائضة) يُسقط
    حصّة. والعلاجُ بياناتٌ لا خوارزميّة: تفريغٌ واحدٌ أقلّ.
    """
    from .preference_capacity import weekly_capacity
    from .scheduler import LAST_PERIOD

    load: dict[str, int] = defaultdict(int)
    for t in tasks:
        for m in t.members:
            load[m.teacher_id] += t.span
    blocked_per_day: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for teacher_id, day, _period in blocked_slots:
        blocked_per_day[teacher_id][day] += 1
    by_teacher = {str(p.teacher_id): p for p in prefs}
    advice, seen = [], set()
    for task in leftovers:
        for m in task.members:
            pref = by_teacher.get(m.teacher_id)
            if pref is None or m.teacher_id in seen:
                continue
            seen.add(m.teacher_id)
            free = {d: LAST_PERIOD - n for d, n in blocked_per_day[m.teacher_id].items()}
            capacity = weekly_capacity(
                pref.max_daily_periods, pref.max_consecutive, pref.max_gap, pref.free_day, free
            )
            if capacity - load[m.teacher_id] <= 1:
                advice.append(
                    f"قيودُ {m.teacher_name} تسع {capacity} حصّةً ونصابُه {load[m.teacher_id]} — "
                    "بلا هامش، فأيُّ قيدٍ آخر يُسقط حصّة: أزل تفريغاً واحداً أو ارفع سقفاً "
                    "ليكتمل الجدول"
                )
    return advice


def _capacity_shortfalls(tasks: list[Task], prefs: Any, blocked_slots: set) -> list[str]:
    """معلّمون تسع قيودُهم أقلَّ من نصابهم — بالحساب لا بالتخمين."""
    from .preference_capacity import explain_shortfall, weekly_capacity
    from .scheduler import LAST_PERIOD

    load: dict[str, int] = defaultdict(int)
    names: dict[str, str] = {}
    for t in tasks:
        for m in t.members:
            load[m.teacher_id] += t.span
            names[m.teacher_id] = m.teacher_name
    blocked_per_day: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for teacher_id, day, _period in blocked_slots:
        blocked_per_day[teacher_id][day] += 1

    found = []
    for pref in prefs:
        tid = str(pref.teacher_id)
        if tid not in load:
            continue
        free_per_day = {d: LAST_PERIOD - n for d, n in blocked_per_day[tid].items()}
        capacity = weekly_capacity(
            pref.max_daily_periods,
            pref.max_consecutive,
            pref.max_gap,
            pref.free_day,
            free_per_day,
        )
        if capacity < load[tid]:
            found.append(explain_shortfall(names[tid], capacity, load[tid], pref))
    return found


def _day_coverage(tasks: list[Task], blocked_slots: set) -> dict:
    """{معلّم: (نصابُه، أيّامُه المتاحة)} — واليومُ المفرَّغُ كاملاً ليس متاحاً.

    قرارُ الإدارة 2026-09-04: حصصُ المعلّم على أيّام الأسبوع كلِّها، لا يومَ
    بلا حصّة إلّا بتفريغٍ من الإعدادات. ومن نصابُه دون عدد أيّامه (منسّقٌ
    بأربع حصص) مستثنىً بالضرورة — والقيدُ لا يمسّه.
    """
    from .scheduler import DAYS, LAST_PERIOD

    placements: dict[str, int] = defaultdict(int)
    periods: dict[str, int] = defaultdict(int)
    for t in tasks:
        for m in t.members:
            placements[m.teacher_id] += 1
            periods[m.teacher_id] += t.span
    blocked_per_day: dict[tuple[str, int], int] = defaultdict(int)
    for teacher_id, day, _period in blocked_slots:
        blocked_per_day[(teacher_id, day)] += 1
    return {
        tid: (
            count,
            periods[tid],
            frozenset(d for d in DAYS if blocked_per_day[(tid, d)] < LAST_PERIOD),
        )
        for tid, count in placements.items()
    }
