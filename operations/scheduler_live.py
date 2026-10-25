"""scheduler_live.py — الجدولُ القائم شبكةً في الذاكرة، لسداده بأقلّ اضطراب (SCH-06).

إصلاحُ اثنتي عشرةَ مخالفةً بتوليدٍ من الصفر يُعيد ترتيبَ ثمانمئةٍ وتسعٍ وستّين
حصّة، فيتغيّر جدولُ كلّ معلّمٍ وكلّ شعبةٍ ليصلح بعضُها. والممارسةُ المعتمدةُ في
جداول منتصف العام «أقلُّ اضطراب»: يُحمَّل الجدولُ كما هو، وتتحرّك الحصصُ
المخالفةُ ومن يلزم تحريكُه معها وحدَهم.

فهنا تُبنى المهامُّ من الإسنادات كما يبنيها التوليد (`build_tasks`)، ثمّ تُسكَن
كلُّ مهمّةٍ في خانتها من حصص الجدول: الشعبةُ والمعلّمون والمادّةُ هم البصمة،
والمزدوجةُ تأخذ خانتين متتاليتين ببصمةٍ واحدة. وما لا يُطابَق يُقال باسمه ولا
يُخمَّن له موضع.

ثمّ `settle_live` يسدّد الشبكةَ ويكتبها **مسودّةً جديدةً** حصصُها مطفأة: الحيُّ لا
يُمَسّ، والاعتمادُ طريقُه المعتاد (`ScheduleService.approve_generation`) بعد أن يرى
النائبُ الفرقَ — فالإنسانُ في الحلقة، وأمرُ الإدارة لا ينشر شيئاً بنفسه.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from .models import ScheduleGeneration, ScheduleSlot
from .schedule_grid_loader import _signature, entries_of, load_grid  # noqa: F401
from .scheduler import (
    DAY_NAMES,
    ScheduleGrid,
)
from .scheduler_audit import grid_breaches, summary
from .scheduler_constraints import calculate_quality_score, joinable_pairs_cached
from .scheduler_persist import slots_from_grid
from .scheduler_settle import settle

if TYPE_CHECKING:
    from core.models import CustomUser, School

logger = logging.getLogger(__name__)

#: كم يُسمّى من اليتامى في رسالة الرفض — والعددُ الكاملُ يُقال معه.
ORPHANS_SHOWN = 10


class LiveScheduleError(Exception):
    """جدولٌ حيٌّ لا يُسدَّد كما هو — السببُ يُقال باسمه، ولا يُكتب شيء."""


def cell_labels(grid: ScheduleGrid) -> dict[tuple, tuple[str, str]]:
    """(شعبة، يوم، حصّة) → (اسمُ الشعبة، «المادّة/المعلّم» لساكنيها) — ليُقرأ الفرقُ بالأسماء."""
    out = {}
    for entry in grid.all_entries():
        task = entry["task"]
        label = " + ".join(sorted(f"{m.subject_name}/{m.teacher_name}" for m in task.members))
        for slot in task.slots(entry["period"]):
            out[(task.class_id, entry["day"], slot)] = (task.class_name, label)
    return out


def cell_changes(before: dict, after: dict) -> list[dict]:
    """الخاناتُ التي تغيّر ساكنُها — بالشعبة فاليوم فالحصّة، والخانةُ الفارغةُ نصٌّ فارغ."""
    rows = []
    for key in before.keys() | after.keys():
        was, now = before.get(key, ("", "")), after.get(key, ("", ""))
        if was[1] != now[1]:
            _class_id, day, period = key
            rows.append(
                {
                    "class": was[0] or now[0],
                    "day": day,
                    "period": period,
                    "before": was[1],
                    "after": now[1],
                }
            )
    return sorted(rows, key=lambda r: (r["class"], r["day"], r["period"]))


def _orphans_message(loaded: dict) -> str:
    """لماذا لا يُسدَّد — بالأسماء. والمسودّةُ تُكتب من الشبكة، فخانةٌ بلا إسنادٍ كانت
    ستسقط منها صامتة، وإسنادٌ بلا خانةٍ كان سيبقى بلا حصّةٍ أو يُخمَّن له موضع."""
    tasks, cells = loaded["orphan_tasks"], loaded["orphan_cells"]
    names = {t.class_id: t.class_name for t in loaded["tasks"] + tasks}
    lines = [
        f"الجدولُ الحيّ لا يطابق الإسنادات: {len(tasks)} حصّةَ إسنادٍ بلا خانة، "
        f"و{len(cells)} خانةً بلا إسناد — صالِحهما ثمّ أعِد السداد."
    ]
    lines += [
        f"  إسنادٌ بلا خانة: {t.class_name} · {t.subject_name} ({t.teacher_name})"
        for t in tasks[:ORPHANS_SHOWN]
    ]
    lines += [
        f"  خانةٌ بلا إسناد: {names.get(c, c[:8])} · {DAY_NAMES.get(d, d)} · ح{p}"
        for c, d, p in cells[:ORPHANS_SHOWN]
    ]
    return "\n".join(lines)


def _slot_key(slot: ScheduleSlot) -> tuple:
    return (
        str(slot.class_group_id),
        slot.day_of_week,
        slot.period_number,
        str(slot.teacher_id),
        str(slot.subject_id),
    )


@joinable_pairs_cached()
def settle_live(
    school: School,
    academic_year: str,
    *,
    budget: float = 240.0,
    dry_run: bool = True,
    user: CustomUser | None = None,
) -> dict:
    """يسدّد الجدولَ الحيّ بأقلّ اضطراب — ويكتبه مسودّةً جديدةً إن لم يكن العرضُ جافّاً.

    يُعيد: `source` التوليدُ المعتمد، و`slots` عددُ الحصص الحيّة، و`before`/`after`
    ملخّصُ المدقّق، و`settlement` ما فعله السداد، و`changes` الخاناتُ المتغيّرة،
    و`generation` المسودّةُ الجديدةُ أو `None`. والجرسُ يُقرأ مرّةً للعمليّة كلِّها
    كما في التوليد: المدقّقُ والسدادُ يسألان عنه آلافَ المرّات.
    """
    started = time.time()
    live = ScheduleSlot.objects.filter(school=school, academic_year=academic_year, is_active=True)
    slots = list(live)
    if not slots:
        raise LiveScheduleError(f"لا جدولَ حيّاً للعام {academic_year} — لا شيءَ يُسدَّد.")
    loaded = load_grid(school, academic_year, slots)
    if loaded["orphan_tasks"] or loaded["orphan_cells"]:
        raise LiveScheduleError(_orphans_message(loaded))

    grid, tasks, blocked = loaded["grid"], loaded["tasks"], loaded["blocked"]
    cells_before = cell_labels(grid)
    before = summary(grid_breaches(grid, tasks, blocked))
    settlement = settle(grid, tasks, blocked, loaded["preferences"], school, time.time() + budget)
    outcome = {
        "source": ScheduleGeneration.objects.filter(
            school=school, academic_year=academic_year, status="approved"
        )
        .order_by("-generated_at")
        .first(),
        "slots": len(slots),
        "before": before,
        "after": summary(grid_breaches(grid, tasks, blocked)),
        "settlement": settlement,
        "changes": cell_changes(cells_before, cell_labels(grid)),
        "generation": None,
        "budget_seconds": budget,
        "elapsed_ms": int((time.time() - started) * 1000),
    }
    # لا فرقَ فلا مسودّة: التشغيلُ الثاني على جدولٍ سُدِّد لا يكتب نسخةً منه.
    if dry_run or not outcome["changes"]:
        return outcome
    with transaction.atomic():
        # والسدادُ دقائق: جدولٌ اعتُمد في أثنائها يجعل المسودّةَ سداداً لجدولٍ لم يعد حيّاً.
        if set(live.values_list("id", flat=True)) != {s.id for s in slots}:
            raise LiveScheduleError("تغيّر الجدولُ الحيّ أثناء السداد — أعِد التشغيلَ على الجديد.")
        outcome["generation"] = _write_draft(school, academic_year, loaded, slots, outcome, user)
    return outcome


def _write_draft(
    school: School,
    academic_year: str,
    loaded: dict,
    slots: list[ScheduleSlot],
    outcome: dict,
    user: CustomUser | None,
) -> ScheduleGeneration:
    """صفُّ المسودّة وحصصُها المطفأة وسطرُ التدقيق — في معاملة المُنادي."""
    from core.models import AuditLog
    from operations.schedule_lab import store_metrics

    grid, tasks, preferences = loaded["grid"], loaded["tasks"], loaded["preferences"]
    required = sum(t.span * len(t.members) for t in tasks)
    quality = calculate_quality_score(grid, preferences, total_required=required)
    source = outcome["source"]
    generation = ScheduleGeneration.objects.create(
        school=school,
        academic_year=academic_year,
        generated_by=user,
        status="draft",
        quality_score=quality["score"],
        hard_violations=outcome["after"]["count"],
        soft_violations=quality["violations"],
        total_slots_created=quality["total_slots"],
        generation_time_ms=outcome["elapsed_ms"],
        finished_at=timezone.now(),
        config_snapshot={
            #: سدادٌ (`settle`) أو تكييفٌ بعد تغيير إسناد (`adapt`) لا توليد — والمصدرُ يُذكر ليُقارَن به.
            "mode": outcome.get("mode", "settle"),
            "source_generation": str(source.id) if source else None,
            "total_tasks": len(tasks),
            "budget_seconds": outcome["budget_seconds"],
            "settlement": [outcome["settlement"]],
            "breaches_before": outcome["before"],
            "breaches": outcome["after"],
            "changed_cells": len(outcome["changes"]),
            "preferences_count": len(preferences),
            "constraints": grid.policy.as_dict(),
        },
    )
    # ملاحظةٌ كُتبت يدويّاً على حصّةٍ حيّةٍ تتبعها ما بقيت في خانتها.
    notes = {_slot_key(s): s.notes for s in slots if s.notes}
    rows = slots_from_grid(school, academic_year, grid, generation, publish=False)
    for row in rows:
        row.notes = notes.get(_slot_key(row), "")
    ScheduleSlot.objects.bulk_create(rows)
    AuditLog.objects.create(
        school=school,
        user=user,
        action="create",
        model_name="other",
        object_id=str(generation.pk),
        object_repr=f"مسودّةُ سداد الجدول {academic_year}"[:300],
        changes={
            "event": "schedule_settle_draft",
            "source_generation": str(source.id) if source else None,
            "breaches": [outcome["before"]["count"], outcome["after"]["count"]],
            "changed_cells": len(outcome["changes"]),
        },
    )
    # مؤشّراتُ المختبر كما يحسبها العاملُ بعد التوليد — ونقطةُ حفظٍ تحميها: القياسُ
    # لا يُسقط مسودّةً صحيحة.
    try:
        with transaction.atomic():
            store_metrics(generation)
    except Exception:  # noqa: BLE001
        logger.exception("schedule_lab: تعذّر القياسُ لمسودّة السداد %s", generation.pk)
    return generation
