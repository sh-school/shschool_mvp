"""scheduler_adapt.py — تكييفُ الجدول الحيّ بعد تغيير إسنادٍ بأقلّ اضطراب (SCH-14).

يتغيّر الإسنادُ بعد اعتماد الجدول: معلّمٌ جديدٌ لمادّةٍ في شعبة، أو نصابٌ يزيد، أو معلّمٌ
يُنقل. والطريقُ الوحيدُ اليوم توليدٌ كاملٌ يعيد ترتيبَ ثمانمئةٍ وتسعٍ وستّين حصّةً ليتغيّر
إسنادٌ واحد — وقد وقف المعلّمون على جدولهم. والممارسةُ المعتمدةُ لجداول منتصف العام:
**يُثبَّت ما لم يتغيّر، ويُوضَع الجديدُ وحدَه**، فيتغيّر أقلُّ ما يمكن.

فهنا يُبنى الجدولُ الحيّ شبكةً (`scheduler_live.load_grid`)، والحصصُ التي لا خانةَ لها (إسنادٌ
جديدٌ أو معدَّل) تُوضع على مرحلتين:

    ١. الوراثة   خاناتُ الإسناد القديم في الشعبة والمادّة نفسِها تُعرَض أوّلاً على الجديد —
                 تبديلُ معلّمٍ لمادّةٍ يبقى في خاناتها، فلا يتحرّك أحدٌ سواهما.
    ٢. البحث     ما لم يجد ورثةً يُوضع بمسارات التوليد نفسِها (جشعٌ ثمّ إزاحةٌ موجَّهة)
                 بالقيود الصلبة كلِّها — وتوزيعُ المادّة لا يُكسَر (D-17).

وما لم يجد موضعاً يُقال باسمه وأكثرِ ما منعه (`unplaced_message`) ولا تُكتب مسودّةٌ ناقصة:
جدولٌ ينقص حصّةً لا يُعرض على من يعتمد. والكتابةُ مسودّةٌ جديدةٌ كسدادِ الجدول الحيّ: الحيُّ لا
يُمَسّ، والاعتمادُ من صفحة الجدول الذكيّ.
"""

from __future__ import annotations

import random
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from django.db import transaction

from .models import ScheduleGeneration, ScheduleSlot
from .scheduler import _greedy_pass, _repair_pass, sort_tasks
from .scheduler_audit import grid_breaches, summary, unplaced_message
from .scheduler_constraints import joinable_pairs_cached
from .scheduler_improve import _fits
from .scheduler_live import (
    LiveScheduleError,
    _write_draft,
    cell_changes,
    cell_labels,
    load_grid,
)
from .scheduler_settle import settle_safely

if TYPE_CHECKING:
    from core.models import CustomUser, School

    from .scheduler import Task


def slot_labels(slots: list[ScheduleSlot]) -> dict[tuple, tuple[str, str]]:
    """(شعبة، يوم، حصّة) → (اسمُ الشعبة، «المادّة/المعلّم») للحصص القائمة — لتُقارَن بالناتج.

    وشبكةُ `load_grid` تُسقط الخاناتِ التي لا إسنادَ لها، فلا تصلح «قبلاً» لهذا الفرق: تُقرأ
    من الحصص نفسِها.
    """
    labels: dict[tuple, list[str]] = defaultdict(list)
    names: dict[tuple, str] = {}
    for slot in slots:
        key = (str(slot.class_group_id), slot.day_of_week, slot.period_number)
        names[key] = str(slot.class_group)
        subject = slot.subject.name_ar if slot.subject else ""
        labels[key].append(f"{subject}/{slot.teacher.full_name}")
    return {key: (names[key], " + ".join(sorted(parts))) for key, parts in labels.items()}


def _inherit(grid: Any, orphans: list[Task], freed: list[tuple], slots: list, blocked: Any) -> int:
    """يعرض خاناتِ الإسناد القديم على الجديد في الشعبة والمادّة نفسِها — كم وُرِّث منها."""
    by_cell = {(str(s.class_group_id), s.day_of_week, s.period_number): s for s in slots}
    held: dict[tuple, list[tuple[int, int]]] = defaultdict(list)
    for class_id, day, period in freed:
        slot = by_cell.get((class_id, day, period))
        if slot is not None and slot.subject_id:
            held[(class_id, str(slot.subject_id))].append((day, period))
    inherited = 0
    for task in orphans:
        cells = held.get((str(task.class_id), str(task.subject_id)), [])
        for day, period in sorted(cells):
            if grid.home_of(task) is not None:
                break
            wanted = all((day, period + step) in cells for step in range(1, task.span))
            if wanted and _fits(grid, task, blocked, day, period):
                grid.place(day, period, task)
                inherited += 1
    return inherited


@joinable_pairs_cached()
def adapt_live(
    school: School,
    academic_year: str,
    *,
    budget: float = 120.0,
    dry_run: bool = True,
    user: CustomUser | None = None,
    settle_after: bool = False,
) -> dict:
    """يُكيّف الجدولَ الحيّ مع الإسنادات الحاليّة بأقلّ تغيير — ويكتبه مسودّةً إن لم يكن العرضُ جافّاً.

    يُعيد ما يُعيده `settle_live` (`source`، `slots`، `before`/`after`، `changes`، `generation`)
    وزيادةً: `orphan_tasks` و`orphan_cells` و`placed` و`unplaced` (رسائلُ بأسبابها).

    و`settle_after` يُتبع الوضعَ بسدادٍ للجدول كلِّه: الحصصُ الجديدةُ قد تُوضع برخصة التلاصق فتزيد
    المخالفاتِ، والسدادُ يُنزلها — لكنّه يمسّ خاناتٍ لم تتغيّر إسنادُها، فهو خيارٌ لا افتراض.
    """
    started = time.time()
    live = ScheduleSlot.objects.filter(school=school, academic_year=academic_year, is_active=True)
    slots = list(live.select_related("class_group", "subject", "teacher"))
    if not slots:
        raise LiveScheduleError(f"لا جدولَ حيّاً للعام {academic_year} — لا شيءَ يُكيَّف.")
    loaded = load_grid(school, academic_year, slots)
    orphans, freed = loaded["orphan_tasks"], loaded["orphan_cells"]
    if not orphans and not freed:
        raise LiveScheduleError("الجدولُ الحيّ يطابق الإسناداتِ — لا شيءَ يُكيَّف.")

    grid, tasks, blocked, prefs = (
        loaded["grid"],
        loaded["tasks"],
        loaded["blocked"],
        loaded["preferences"],
    )
    before = summary(grid_breaches(grid, tasks, blocked))
    inherited = _inherit(grid, orphans, freed, slots, blocked)
    pending = sort_tasks([t for t in orphans if grid.home_of(t) is None], blocked)

    left = _greedy_pass(grid, pending, blocked, prefs, school, random.Random(0))
    for licences in ({}, {"allow_adjacent": True}, {"allow_adjacent": True, "allow_dense": True}):
        if not left:
            break
        left = _repair_pass(grid, left, blocked, prefs, 500, school, **licences)

    settled: dict = {}
    if settle_after:
        # السدادُ قد يفتح للمتعذّرة موضعاً لم يكن: يُعاد عليها البحثُ بعده.
        placed_now = [t for t in orphans if grid.home_of(t) is not None]
        settled = settle_safely(
            grid, tasks + placed_now, blocked, prefs, school, time.time() + budget
        )
        if left:
            left = _repair_pass(grid, left, blocked, prefs, 500, school, allow_adjacent=True)
    placed = [t for t in orphans if grid.home_of(t) is not None]
    outcome = {
        "mode": "adapt",
        "source": ScheduleGeneration.objects.filter(
            school=school, academic_year=academic_year, status="approved"
        )
        .order_by("-generated_at")
        .first(),
        "slots": len(slots),
        "before": before,
        "after": summary(grid_breaches(grid, tasks + placed, blocked)),
        "settlement": {
            "moves": {
                "inherited": inherited,
                "searched": len(placed) - inherited,
                **settled.get("moves", {}),
            },
            "timed_out": settled.get("timed_out", False),
        },
        "changes": cell_changes(slot_labels(slots), cell_labels(grid)),
        "generation": None,
        "budget_seconds": budget,
        "elapsed_ms": int((time.time() - started) * 1000),
        "orphan_tasks": len(orphans),
        "orphan_cells": len(freed),
        "placed": len(placed),
        "unplaced": [unplaced_message(grid, task, blocked) for task in left],
    }
    loaded["tasks"] = tasks + placed
    # جدولٌ ينقص حصّةً لا يُكتب مسودّةً: يُقال ما تعذّر وبأيّ سبب، ويُصلَح الإسنادُ أو القيدُ أوّلاً.
    if dry_run or outcome["unplaced"] or not outcome["changes"]:
        return outcome
    with transaction.atomic():
        if set(live.values_list("id", flat=True)) != {s.id for s in slots}:
            raise LiveScheduleError("تغيّر الجدولُ الحيّ أثناء التكييف — أعِد التشغيلَ على الجديد.")
        outcome["generation"] = _write_draft(school, academic_year, loaded, slots, outcome, user)
    return outcome
