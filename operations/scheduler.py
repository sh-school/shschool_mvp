"""
scheduler.py — خوارزمية التوليد الذكية للجدول الأسبوعي
Greedy + Backtracking + Local Search
مدرسة الشحانية — قطر 2025-2026
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field

from django.conf import settings
from django.db import transaction

from core.models import ClassGroup, School
from .models import (
    ScheduleGeneration,
    ScheduleSlot,
    SubjectClassAssignment,
    TeacherPreference,
    TimeSlotConfig,
)
from .scheduler_constraints import (
    SoftPenalty,
    calculate_quality_score,
    evaluate_soft_constraints,
    is_slot_valid,
)

logger = logging.getLogger(__name__)

DAYS = [0, 1, 2, 3, 4]  # أحد - خميس
DAY_NAMES = {0: "الأحد", 1: "الاثنين", 2: "الثلاثاء", 3: "الأربعاء", 4: "الخميس"}


@dataclass
class Task:
    """مهمة جدولة: مادة × فصل × معلم"""
    class_id: str
    class_name: str
    subject_id: str
    subject_name: str
    subject_code: str
    teacher_id: str
    teacher_name: str
    weekly_periods: int
    requires_lab: bool = False
    preferred_periods: list = field(default_factory=list)


class ScheduleGrid:
    """شبكة الجدول: 5 أيام × 7 حصص"""

    def __init__(self):
        # grid[day][period] = list of {task, ...}
        self._grid: dict[int, dict[int, dict | None]] = {}
        # فهارس سريعة
        self._teacher_slots: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self._class_slots: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self._subject_class_day: dict[tuple[str, str, int], int] = defaultdict(int)
        self._entries: list[dict] = []

        for d in DAYS:
            self._grid[d] = {}
            max_p = 6 if d == 4 else 7
            for p in range(1, max_p + 1):
                self._grid[d][p] = None

    def place(self, day: int, period: int, task: Task):
        """وضع حصة في الشبكة"""
        self._grid[day][period] = task
        self._teacher_slots[task.teacher_id].append((day, period))
        self._class_slots[task.class_id].append((day, period))
        self._subject_class_day[(task.subject_id, task.class_id, day)] += 1
        self._entries.append({"day": day, "period": period, "task": task})

    def remove(self, day: int, period: int):
        """إزالة حصة (للتراجع)"""
        task = self._grid[day][period]
        if task is None:
            return
        self._grid[day][period] = None
        self._teacher_slots[task.teacher_id].remove((day, period))
        self._class_slots[task.class_id].remove((day, period))
        key = (task.subject_id, task.class_id, day)
        self._subject_class_day[key] -= 1
        self._entries = [e for e in self._entries if not (e["day"] == day and e["period"] == period)]

    def teacher_at(self, day: int, period: int) -> str | None:
        """معرف المعلم في خانة معينة"""
        t = self._grid.get(day, {}).get(period)
        return t.teacher_id if t else None

    def class_at(self, day: int, period: int) -> str | None:
        """معرف الفصل في خانة معينة"""
        t = self._grid.get(day, {}).get(period)
        return t.class_id if t else None

    def teacher_periods_on_day(self, teacher_id: str, day: int) -> int:
        """عدد حصص المعلم في يوم"""
        return sum(1 for d, p in self._teacher_slots[teacher_id] if d == day)

    def class_periods_on_day(self, class_id: str, day: int) -> int:
        """عدد حصص الفصل في يوم"""
        return sum(1 for d, p in self._class_slots[class_id] if d == day)

    def subject_on_day(self, class_id: str, subject_id: str, day: int) -> int:
        """عدد حصص مادة لفصل في يوم"""
        return self._subject_class_day.get((subject_id, class_id, day), 0)

    def teacher_consecutive_at(self, teacher_id: str, day: int, period: int) -> int:
        """عدد الحصص المتتالية للمعلم عند إضافة حصة في period"""
        count = 0
        for p in range(period - 1, 0, -1):
            if self.teacher_at(day, p) == teacher_id:
                count += 1
            else:
                break
        for p in range(period + 1, 8):
            if self.teacher_at(day, p) == teacher_id:
                count += 1
            else:
                break
        return count

    def would_create_gap(self, teacher_id: str, day: int, period: int) -> bool:
        """هل إضافة حصة ستخلق فجوة للمعلم؟"""
        periods_today = sorted(
            p for d, p in self._teacher_slots[teacher_id] if d == day
        )
        periods_today.append(period)
        periods_today.sort()
        if len(periods_today) < 2:
            return False
        for i in range(len(periods_today) - 1):
            diff = periods_today[i + 1] - periods_today[i]
            # فجوة إذا الفرق > 1 (مع مراعاة الاستراحات)
            if diff > 2:
                return True
        return False

    def all_entries(self) -> list[dict]:
        return self._entries

    def get_task_at(self, day: int, period: int) -> Task | None:
        return self._grid.get(day, {}).get(period)


def build_tasks(school: School, academic_year: str) -> list[Task]:
    """بناء قائمة المهام من SubjectClassAssignment"""
    assignments = SubjectClassAssignment.objects.filter(
        school=school, academic_year=academic_year, is_active=True
    ).select_related("class_group", "subject", "teacher")

    tasks = []
    for a in assignments:
        for _ in range(a.weekly_periods):
            tasks.append(Task(
                class_id=str(a.class_group_id),
                class_name=str(a.class_group),
                subject_id=str(a.subject_id),
                subject_name=a.subject.name_ar,
                subject_code=a.subject.code,
                teacher_id=str(a.teacher_id),
                teacher_name=a.teacher.full_name,
                weekly_periods=a.weekly_periods,
                requires_lab=a.requires_lab,
                preferred_periods=a.preferred_periods or [],
            ))
    return tasks


def sort_tasks(tasks: list[Task]) -> list[Task]:
    """ترتيب المهام: الأصعب أولاً (Most Constrained First)"""
    # عد كم معلم فريد لكل مادة
    subject_teacher_count = defaultdict(set)
    for t in tasks:
        subject_teacher_count[t.subject_id].add(t.teacher_id)

    def priority(task: Task) -> tuple:
        teacher_count = len(subject_teacher_count[task.subject_id])
        return (
            teacher_count,          # معلم وحيد أولاً (1 < 2 < ...)
            -task.weekly_periods,   # نصاب أعلى أولاً
            -int(task.requires_lab), # المعامل أولاً
        )

    return sorted(tasks, key=priority)


def get_available_slots(grid: ScheduleGrid, task: Task) -> list[tuple[int, int]]:
    """الخانات المتاحة (تحقق قيود صلبة فقط)"""
    available = []
    for day in DAYS:
        max_p = 6 if day == 4 else 7
        for period in range(1, max_p + 1):
            if grid.get_task_at(day, period) is not None:
                continue
            if is_slot_valid(grid, day, period, task):
                available.append((day, period))
    return available


def rank_slots(
    grid: ScheduleGrid,
    task: Task,
    available: list[tuple[int, int]],
    preferences: dict | None = None,
) -> list[tuple[int, int, float]]:
    """ترتيب الخانات حسب أقل عقوبات مرنة"""
    ranked = []
    for day, period in available:
        penalty = evaluate_soft_constraints(grid, day, period, task, preferences)
        ranked.append((day, period, penalty.total))
    ranked.sort(key=lambda x: x[2])
    return ranked


def generate_schedule(
    school: School,
    academic_year: str,
    user=None,
    max_backtrack: int = 500,
) -> dict:
    """
    التوليد الرئيسي — Greedy + Backtracking

    Returns:
        dict with keys: success, grid, quality, generation, errors
    """
    start_time = time.time()
    errors = []

    # 1. بناء المهام
    tasks = build_tasks(school, academic_year)
    if not tasks:
        return {"success": False, "errors": ["لا توجد توزيعات مواد (SubjectClassAssignment). أضف التوزيعات أولاً."]}

    # 2. تحميل التفضيلات
    prefs_qs = TeacherPreference.objects.filter(school=school, academic_year=academic_year)
    preferences = {}
    for p in prefs_qs:
        preferences[str(p.teacher_id)] = {
            "max_daily": p.max_daily_periods,
            "max_consecutive": p.max_consecutive,
            "free_day": p.free_day,
        }

    # 3. ترتيب المهام
    sorted_tasks = sort_tasks(tasks)

    # 4. التوليد
    grid = ScheduleGrid()
    backtrack_count = 0
    placed = []
    i = 0

    while i < len(sorted_tasks):
        task = sorted_tasks[i]
        available = get_available_slots(grid, task)
        ranked = rank_slots(grid, task, available, preferences)

        if ranked:
            day, period, penalty = ranked[0]
            grid.place(day, period, task)
            placed.append((i, day, period))
            i += 1
        else:
            # Backtrack
            if not placed or backtrack_count >= max_backtrack:
                errors.append(f"تعذر وضع: {task.subject_name} → {task.class_name} ({task.teacher_name})")
                i += 1
                continue
            backtrack_count += 1
            last_i, last_day, last_period = placed.pop()
            grid.remove(last_day, last_period)
            i = last_i  # إعادة محاولة

    elapsed_ms = int((time.time() - start_time) * 1000)

    # 5. حساب الجودة
    quality = calculate_quality_score(grid, preferences)

    # 6. حفظ النتائج
    generation = None
    if not errors or quality["total_slots"] > 0:
        with transaction.atomic():
            # حذف الجدول القديم
            ScheduleSlot.objects.filter(
                school=school, academic_year=academic_year, is_active=True
            ).update(is_active=False)

            # إنشاء الحصص الجديدة
            time_config = {}
            for tc in TimeSlotConfig.objects.filter(school=school, day_type="regular", is_break=False):
                time_config[tc.period_number] = (tc.start_time, tc.end_time)

            bulk = []
            for entry in grid.all_entries():
                t = entry["task"]
                d = entry["day"]
                p = entry["period"]
                start, end = time_config.get(p, ("07:10", "07:55"))
                bulk.append(ScheduleSlot(
                    school=school,
                    teacher_id=t.teacher_id,
                    class_group_id=t.class_id,
                    subject_id=t.subject_id,
                    day_of_week=d,
                    period_number=p,
                    start_time=start,
                    end_time=end,
                    academic_year=academic_year,
                    is_active=True,
                ))
            ScheduleSlot.objects.bulk_create(bulk)

            # سجل التوليد
            generation = ScheduleGeneration.objects.create(
                school=school,
                academic_year=academic_year,
                generated_by=user,
                status="draft",
                quality_score=quality["score"],
                hard_violations=len(errors),
                soft_violations=quality["violations"],
                total_slots_created=quality["total_slots"],
                generation_time_ms=elapsed_ms,
                config_snapshot={
                    "total_tasks": len(tasks),
                    "backtrack_count": backtrack_count,
                    "preferences_count": len(preferences),
                },
            )

    return {
        "success": len(errors) == 0,
        "grid": grid,
        "quality": quality,
        "generation": generation,
        "errors": errors,
        "elapsed_ms": elapsed_ms,
        "total_tasks": len(tasks),
        "backtrack_count": backtrack_count,
    }
