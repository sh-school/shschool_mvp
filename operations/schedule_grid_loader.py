"""schedule_grid_loader.py — الجدولُ القائم شبكةً في الذاكرة (يعتمد عليه المقيِّمُ المستقلّ).

مستخرَجٌ حرفياً من `scheduler_live` (W-20261010-004، المرحلة 1) ليبقى بعد حذف المحرّك السابق.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import TYPE_CHECKING

from .models import ScheduleSlot
from .scheduler_bell import joinable_pairs
from .scheduling_inputs import (
    ScheduleGrid,
    _day_coverage,
    build_tasks,
    load_band_times,
    load_break_times,
    load_inputs,
)

if TYPE_CHECKING:
    from core.models import School


def _signature(pairs: Iterable[tuple]) -> frozenset:
    return frozenset((str(t), str(s)) for t, s in pairs)


def load_grid(school: School, academic_year: str, slots: Iterable[ScheduleSlot]) -> dict:
    """يبني الشبكةَ من حصصٍ قائمة (حيّةٍ أو مسودّة).

    يُعيد: الشبكة، والمهامّ الموضوعة، والتفريغات، والتفضيلات، وما لم يُطابَق —
    `orphan_tasks` مهامُّ إسنادٍ بلا حصّة، و`orphan_cells` خاناتٌ بلا إسناد.
    """
    from . import constraint_registry

    tasks = build_tasks(school, academic_year)
    _prefs_qs, preferences, blocked = load_inputs(school, academic_year)
    grid = ScheduleGrid(
        band_times=load_band_times(school),
        coverage=_day_coverage(tasks, blocked),
        break_times=load_break_times(school),
        policy=constraint_registry.resolve(school, academic_year),
    )

    # الخانات: (شعبة، يوم، حصّة) → بصمةُ ساكنيها
    cells: dict[tuple, list] = defaultdict(list)
    for slot in slots:
        cells[(str(slot.class_group_id), slot.day_of_week, slot.period_number)].append(
            (slot.teacher_id, slot.subject_id)
        )
    cell_sig = {key: _signature(pairs) for key, pairs in cells.items()}

    pool: dict[tuple, list] = defaultdict(list)
    for task in tasks:
        sig = _signature((m.teacher_id, m.subject_id) for m in task.members)
        pool[(str(task.class_id), sig, task.span)].append(task)

    placed, orphan_cells, taken = [], [], set()
    for (class_id, day, period), sig in sorted(cell_sig.items()):
        if (class_id, day, period) in taken:
            continue
        nxt = (class_id, day, period + 1)
        double = pool.get((class_id, sig, 2))
        # خانتان بالبصمة نفسها لا تصيران مزدوجةً إلّا إن اتّصلتا بالساعة: مفردةٌ في الأولى
        # ومزدوجةٌ في الثانية والثالثة كانت تُقرأ مزدوجةً في الأولى والثانية فتُعبَر بها فسحة.
        if (
            double
            and cell_sig.get(nxt) == sig
            and nxt not in taken
            and (period, period + 1) in joinable_pairs(school, double[-1].band_id)
        ):
            task = double.pop()
            taken.add(nxt)
        elif pool.get((class_id, sig, 1)):
            task = pool[(class_id, sig, 1)].pop()
        else:
            orphan_cells.append((class_id, day, period))
            continue
        taken.add((class_id, day, period))
        grid.place(day, period, task)
        placed.append(task)

    return {
        "grid": grid,
        "tasks": placed,
        "blocked": blocked,
        "preferences": preferences,
        "orphan_tasks": [t for group in pool.values() for t in group],
        "orphan_cells": orphan_cells,
    }


def entries_of(grid: ScheduleGrid) -> set[tuple]:
    """(شعبة، يوم، حصّة، معلّم، مادّة) لكلّ خانةٍ مشغولة — للمقارنة قبل السداد وبعده."""
    out = set()
    for entry in grid.all_entries():
        task = entry["task"]
        for slot in task.slots(entry["period"]):
            for member in task.members:
                out.add((task.class_id, entry["day"], slot, member.teacher_id, member.subject_id))
    return out
