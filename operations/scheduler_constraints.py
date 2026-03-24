"""
scheduler_constraints.py — القيود الصلبة والمرنة للجدولة الذكية
مدرسة الشحانية الإعدادية الثانوية — قطر 2025-2026
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .scheduler import ScheduleGrid, Task


# ── القيود الصلبة ──────────────────────────────────────────


def check_teacher_conflict(grid: ScheduleGrid, day: int, period: int, teacher_id) -> bool:
    """HC1: المعلم لا يُدرّس فصلين في نفس الوقت"""
    return grid.teacher_at(day, period) != teacher_id


def check_class_conflict(grid: ScheduleGrid, day: int, period: int, class_id) -> bool:
    """HC2: الفصل لا يأخذ مادتين في نفس الوقت"""
    return grid.class_at(day, period) != class_id


def check_day_capacity(grid: ScheduleGrid, day: int, class_id, max_periods: int) -> bool:
    """HC4: لا يتجاوز عدد حصص الفصل في اليوم الحد الأقصى"""
    return grid.class_periods_on_day(class_id, day) < max_periods


def is_slot_valid(grid: ScheduleGrid, day: int, period: int, task: Task) -> bool:
    """تحقق من كل القيود الصلبة لخانة معينة"""
    max_p = 6 if day == 4 else 7  # الخميس = 6 حصص
    if period > max_p:
        return False
    if not check_teacher_conflict(grid, day, period, task.teacher_id):
        return False
    if not check_class_conflict(grid, day, period, task.class_id):
        return False
    return True


# ── القيود المرنة ──────────────────────────────────────────


@dataclass
class SoftPenalty:
    """نتيجة تقييم القيود المرنة لخانة"""

    total: float = 0.0
    details: dict = field(default_factory=dict)

    def add(self, name: str, weight: float, violated: bool):
        if violated:
            self.total += weight
            self.details[name] = weight


def evaluate_soft_constraints(
    grid: ScheduleGrid,
    day: int,
    period: int,
    task: Task,
    preferences: dict | None = None,
) -> SoftPenalty:
    """تقييم القيود المرنة لتحديد أفضل خانة"""
    penalty = SoftPenalty()

    # SC1: تتابع الحصص — لا أكثر من 3 متتالية (وزن 10)
    consecutive = grid.teacher_consecutive_at(task.teacher_id, day, period)
    max_consec = 3
    if preferences and task.teacher_id in preferences:
        max_consec = preferences[task.teacher_id].get("max_consecutive", 3)
    penalty.add("consecutive", 10, consecutive >= max_consec)

    # SC2: فراغات المعلم — تقليل الفجوات (وزن 8)
    creates_gap = grid.would_create_gap(task.teacher_id, day, period)
    penalty.add("gap", 8, creates_gap)

    # SC3: توزيع المادة — لا حصتين نفس المادة نفس اليوم للفصل (وزن 6)
    same_subject_today = grid.subject_on_day(task.class_id, task.subject_id, day)
    penalty.add("subject_spread", 6, same_subject_today > 0)

    # SC4: موازنة الأحمال — تقليل فرق الحصص اليومية للمعلم (وزن 5)
    teacher_today = grid.teacher_periods_on_day(task.teacher_id, day)
    max_daily = 5
    if preferences and task.teacher_id in preferences:
        max_daily = preferences[task.teacher_id].get("max_daily", 5)
    penalty.add("daily_load", 5, teacher_today >= max_daily)

    # SC5: المواد الأساسية في الحصص الأولى (وزن 3)
    is_core = task.subject_code in ("ARA", "ENG", "MAT", "SCI", "CHM", "PHY", "BIO")
    penalty.add("core_early", 3, is_core and period >= 6)

    # SC6: البدنية بعد الاستراحة (وزن 2)
    is_pe = task.subject_code == "PE"
    penalty.add("pe_after_break", 2, is_pe and period not in (4, 5))

    return penalty


# ── حساب نقاط الجودة الإجمالية ──────────────────────────


def calculate_quality_score(grid: ScheduleGrid, preferences: dict | None = None) -> dict:
    """حساب نقاط جودة الجدول بعد التوليد الكامل"""
    violations = {
        "consecutive": 0,
        "gap": 0,
        "subject_spread": 0,
        "daily_load": 0,
        "core_early": 0,
        "pe_after_break": 0,
    }
    total_penalty = 0.0
    total_slots = 0

    for entry in grid.all_entries():
        total_slots += 1
        task = entry["task"]
        day = entry["day"]
        period = entry["period"]
        p = evaluate_soft_constraints(grid, day, period, task, preferences)
        total_penalty += p.total
        for k, v in p.details.items():
            violations[k] = violations.get(k, 0) + 1

    # نقاط الجودة: 100 - (العقوبات المرجحة / العدد الكلي)
    max_possible = total_slots * 34  # مجموع أوزان كل القيود المرنة
    if max_possible == 0:
        score = 100.0
    else:
        score = max(0, 100 * (1 - total_penalty / max_possible))

    return {
        "score": round(score, 1),
        "total_slots": total_slots,
        "total_penalty": round(total_penalty, 1),
        "violations": violations,
    }
