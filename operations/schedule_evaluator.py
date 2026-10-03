"""schedule_evaluator.py — المُقيِّم المستقلّ للجدول (V2-S1، ADR-0008 §3 و§5).

يقرأ **أيَّ جدول** — الحيَّ المعتمَد، أو مسودّةَ توليد، أو ناتجَ حلّالٍ خارجيّ بالمعرّفات — ويُخرج:

- `InfeasibilityValue`: حصصُ الإسناد التي لم تُوضع (المطلوبُ − الموضوع)، تُبلَّغ صراحةً ولو كانت صفراً.
- مخالفاتُ كلّ قيدٍ صلب، بحكم `scheduler_audit.grid_breaches` حرفاً: المدقّقُ الرسميّ نفسُه لا نسخةٌ ثانيةٌ
  من القيود تفترق عنه يوماً.
- `ObjectiveValue`: تكلفةُ القيود **المرنة** وحدَها (`calculate_quality_score.total_penalty` بأوزان السياسة)؛
  والصلبةُ منفصلةٌ وشرطُ قبولها صفر.

**الاستقلال عن الباني:** لا يقرأ `config_snapshot` ولا أيَّ عدّادٍ حفظه المولّدُ عن نفسه، ولا يستورد ترميزَ
CP-SAT؛ يُحمِّل الخاناتِ ويبني الشبكةَ ويسأل القيودَ من جديد. والمخرجُ بمعرّفاتٍ مختصرةٍ لا أسماء (شرطُ 0105).

**ما لا يفعله:** لا يكتب في القاعدة، ولا يُرخي سقفاً بصمت (D-166م)، ولا يحكم بأمثليّةٍ لم يثبتها الحلّال.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from .scheduler_audit import grid_breaches
from .scheduler_constraints import calculate_quality_score
from .scheduler_live import entries_of, load_grid

#: حالاتُ الحلّال المقبولةُ في المصدر الخارجيّ — وما سواها يُرفض.
SOLVER_STATUSES = ("OPTIMAL", "FEASIBLE", "UNKNOWN", "INFEASIBLE")

#: ما يقوله المُقيِّمُ عن كلّ حالة (ADR §3.4): البرهانُ غيرُ ضيق الوقت، والحلُّ بلا أمثليّةٍ مُثبَتةٍ ليس أمثل.
VERDICTS = {
    "OPTIMAL": "أمثلُ بحسب الحلّال",
    "FEASIBLE": "حلٌّ غيرُ مُثبَتِ الأمثليّة",
    "INFEASIBLE": "مستحيلٌ بالبرهان",
    "UNKNOWN": "ضيقُ وقتٍ لا استحالة",
}

_TOP_KEYS = frozenset({"solver", "slots"})
_SOLVER_KEYS = frozenset({"status", "seed", "workers", "seconds"})
_SOLVER_REQUIRED = frozenset({"status", "seed", "workers"})


class EvaluatorInputError(ValueError):
    """مدخلٌ خارجيٌّ مرفوض: حقلٌ غيرُ معلَنٍ أو قيمةٌ خارج المدى."""


@dataclass(frozen=True)
class Evaluation:
    placed_periods: int
    required_periods: int
    infeasibility_value: int
    unplaced: tuple[tuple[str, str, str], ...]  # (شعبة، مادّة، معلّم) بمعرّفاتٍ مختصرة
    orphan_cells: int
    hard_breaches: dict[str, int]
    objective_value: float
    soft_counts: dict[str, int]
    fingerprint: str
    solver: dict[str, Any] | None = None
    verdict: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def hard_total(self) -> int:
        return sum(self.hard_breaches.values())

    @property
    def accepted(self) -> bool:
        """شرطُ القبول: لا حصّةَ بلا موضع، ولا مخالفةَ صلبة، ولا خانةَ بلا إسناد."""
        return self.infeasibility_value == 0 and self.hard_total == 0 and self.orphan_cells == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "InfeasibilityValue": self.infeasibility_value,
            "required_periods": self.required_periods,
            "placed_periods": self.placed_periods,
            "unplaced": [list(row) for row in self.unplaced],
            "orphan_cells": self.orphan_cells,
            "hard_breaches": dict(sorted(self.hard_breaches.items())),
            "hard_total": self.hard_total,
            "ObjectiveValue": self.objective_value,
            "soft_counts": dict(sorted(self.soft_counts.items())),
            "accepted": self.accepted,
            "fingerprint": self.fingerprint,
            "solver": self.solver,
            "verdict": self.verdict,
            "notes": list(self.notes),
        }


def short(identifier: object) -> str:
    """معرّفٌ مختصرٌ للعرض — ثمانيةُ أحرفٍ تكفي للتمييز ولا تكشف اسماً."""
    return str(identifier)[:8]


def _check_int(value: object, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise EvaluatorInputError(f"{name}: عددٌ صحيحٌ بين {low} و{high}")
    return value


def slots_from_payload(payload: object) -> tuple[list[SimpleNamespace], dict[str, Any] | None]:
    """يقرأ ناتجَ حلّالٍ خارجيٍّ: معرّفاتٌ لا أسماء، وأيُّ حقلٍ غيرِ معلَنٍ يُرفض.

    الشكل: `{"solver": {"status", "seed", "workers", "seconds"?}, "slots": [[class_id, subject_id,
    teacher_id, day, period], …]}` — صفٌّ لكلّ (شعبة، يوم، حصّة، معلّم، مادّة): الخانةُ المنقسمةُ بين
    معلّمَين لها صفّان بمادّتَيهما.
    """
    if not isinstance(payload, dict) or set(payload) - _TOP_KEYS or "slots" not in payload:
        raise EvaluatorInputError("الجذرُ: solver (اختياري) وslots فقط")
    solver = payload.get("solver")
    if solver is not None:
        if (
            not isinstance(solver, dict)
            or set(solver) - _SOLVER_KEYS
            or _SOLVER_REQUIRED - set(solver)
        ):
            raise EvaluatorInputError("solver: status وseed وworkers (وseconds اختياري) فقط")
        if solver["status"] not in SOLVER_STATUSES:
            raise EvaluatorInputError(f"solver.status: إحدى {', '.join(SOLVER_STATUSES)}")
        _check_int(solver["seed"], "solver.seed", 0, 2**31)
        _check_int(solver["workers"], "solver.workers", 1, 256)
        if "seconds" in solver and (
            isinstance(solver["seconds"], bool) or not isinstance(solver["seconds"], int | float)
        ):
            raise EvaluatorInputError("solver.seconds: رقم")
    rows = payload["slots"]
    if not isinstance(rows, list):
        raise EvaluatorInputError("slots: قائمة")
    slots: list[SimpleNamespace] = []
    for index, row in enumerate(rows):
        if not isinstance(row, list) or len(row) != 5:
            raise EvaluatorInputError(f"slots[{index}]: خمسةُ حقول بالضبط")
        class_id, subject_id, teacher_id, day, period = row
        for label, value in (("شعبة", class_id), ("مادّة", subject_id), ("معلّم", teacher_id)):
            if not isinstance(value, str) or not value:
                raise EvaluatorInputError(f"slots[{index}]: معرّف {label} نصّ")
        slots.append(
            SimpleNamespace(
                class_group_id=class_id,
                subject_id=subject_id,
                teacher_id=teacher_id,
                day_of_week=_check_int(day, f"slots[{index}].day", 0, 4),
                period_number=_check_int(period, f"slots[{index}].period", 1, 9),
            )
        )
    return slots, solver


def fingerprint(grid: Any) -> str:
    """بصمةُ الجدول: تجزئةُ خاناته المرتَّبة — تشغيلان بالمدخلات نفسِها يعطيان البصمةَ نفسَها (ADR §3.5)."""
    rows = sorted(tuple(map(str, row)) for row in entries_of(grid))
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()[:16]


def evaluate_slots(
    school: Any,
    academic_year: str,
    slots: Iterable[Any],
    solver: dict[str, Any] | None = None,
) -> Evaluation:
    """يقيّم خاناتٍ (صفوفَ ScheduleSlot أو ما يشبهها) مقابلَ الإسناد النشط. لا يكتب شيئاً."""
    loaded = load_grid(school, academic_year, list(slots))
    grid, placed_tasks, blocked = loaded["grid"], loaded["tasks"], loaded["blocked"]
    orphans = loaded["orphan_tasks"]

    def periods(task: Any) -> int:
        return task.span * len(task.members)

    placed = sum(periods(t) for t in placed_tasks)
    missing = sum(periods(t) for t in orphans)
    required = placed + missing

    breaches = Counter(b.code for b in grid_breaches(grid, placed_tasks, blocked))
    quality = calculate_quality_score(grid, loaded["preferences"], total_required=required)
    soft = {key: count for key, count in quality["violations"].items() if count}

    notes: list[str] = []
    verdict = ""
    if solver is not None:
        verdict = VERDICTS[solver["status"]]
        if solver["status"] in ("INFEASIBLE", "UNKNOWN") and placed:
            notes.append(
                "حالةُ الحلّال لا تُنتج جدولاً، ومع ذلك وُجدت خانات: يُقاس ما وُجد ولا يُصدَّق الوصف"
            )
    if orphans:
        notes.append("InfeasibilityValue > 0: حصصٌ بلا موضع تُبلَّغ ولا يُرخى لها سقفٌ بصمت (D-166م)")
    if loaded["orphan_cells"]:
        notes.append("خاناتٌ بلا إسنادٍ مطابق: الجدولُ لا يوافق الإسنادَ النشط")

    return Evaluation(
        placed_periods=placed,
        required_periods=required,
        infeasibility_value=missing,
        unplaced=tuple(
            sorted((short(t.class_id), short(t.subject_id), short(t.teacher_id)) for t in orphans)
        ),
        orphan_cells=len(loaded["orphan_cells"]),
        hard_breaches=dict(breaches),
        objective_value=round(float(quality["total_penalty"]), 1),
        soft_counts=soft,
        fingerprint=fingerprint(grid),
        solver=dict(solver) if solver else None,
        verdict=verdict,
        notes=notes,
    )


def live_slots(school: Any, academic_year: str) -> Any:
    from .models import ScheduleSlot

    return ScheduleSlot.objects.filter(school=school, academic_year=academic_year, is_active=True)


def generation_slots(generation: Any) -> Any:
    from .models import ScheduleSlot

    return ScheduleSlot.objects.filter(generation=generation)
