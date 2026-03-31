"""
scheduler.py — خوارزمية التوليد الذكية للجدول الأسبوعي
Multi-Pass Greedy + Swap Search — v3
═══════════════════════════════════════════════════════════
v3: إصلاح جذري — الشبكة تدعم فصول متعددة في نفس الخانة الزمنية.
  كل (يوم, حصة) يمكن أن يحتوي على مهمة لكل فصل (حتى 25 فصل).
  القيود: معلم واحد لا يُدرّس فصلين في نفس الوقت.
"""

from __future__ import annotations

import logging
import random
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import time as dt_time

from django.db import transaction

from core.models import School

from .models import (
    ScheduleGeneration,
    ScheduleSlot,
    Subject,
    SubjectClassAssignment,
    TeacherExemption,
    TeacherPreference,
    TimeSlotConfig,
)
from .scheduler_constraints import (
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
    requires_double: bool = False
    preferred_periods: list = field(default_factory=list)
    level_type: str = ""


class ScheduleGrid:
    """
    شبكة الجدول: 5 أيام × 7 حصص × N فصل.
    كل (يوم, حصة) يمكن أن يحتوي على مهمة واحدة لكل فصل.
    القيد الأساسي: معلم واحد لا يُدرّس فصلين في نفس الوقت.
    """

    def __init__(self):
        # (day, period) → list of tasks (one per class)
        self._cells: dict[tuple[int, int], list[Task]] = defaultdict(list)
        # teacher_id → set of (day, period) where they're teaching
        self._teacher_periods: dict[str, set[tuple[int, int]]] = defaultdict(set)
        # class_id → set of (day, period) where they have a lesson
        self._class_periods: dict[str, set[tuple[int, int]]] = defaultdict(set)
        # (subject_id, class_id, day) → count of lessons
        self._subject_class_day: dict[tuple[str, str, int], int] = defaultdict(int)
        # all placed entries
        self._entries: list[dict] = []

    def place(self, day: int, period: int, task: Task):
        """وضع حصة في الشبكة"""
        self._cells[(day, period)].append(task)
        self._teacher_periods[task.teacher_id].add((day, period))
        self._class_periods[task.class_id].add((day, period))
        self._subject_class_day[(task.subject_id, task.class_id, day)] += 1
        self._entries.append({"day": day, "period": period, "task": task})

    def remove(self, day: int, period: int, task: Task):
        """إزالة حصة محددة (للتبديل)"""
        cell = self._cells.get((day, period), [])
        self._cells[(day, period)] = [t for t in cell if t is not task]
        self._teacher_periods[task.teacher_id].discard((day, period))
        self._class_periods[task.class_id].discard((day, period))
        key = (task.subject_id, task.class_id, day)
        self._subject_class_day[key] = max(0, self._subject_class_day[key] - 1)
        self._entries = [
            e for e in self._entries
            if not (e["day"] == day and e["period"] == period and e["task"] is task)
        ]

    def is_teacher_busy(self, teacher_id: str, day: int, period: int) -> bool:
        """هل المعلم مشغول في (يوم, حصة)؟"""
        return (day, period) in self._teacher_periods[teacher_id]

    def is_class_busy(self, class_id: str, day: int, period: int) -> bool:
        """هل الفصل مشغول في (يوم, حصة)؟"""
        return (day, period) in self._class_periods[class_id]

    def teacher_periods_on_day(self, teacher_id: str, day: int) -> int:
        """عدد حصص المعلم في يوم"""
        return sum(1 for d, p in self._teacher_periods[teacher_id] if d == day)

    def class_periods_on_day(self, class_id: str, day: int) -> int:
        """عدد حصص الفصل في يوم"""
        return sum(1 for d, p in self._class_periods[class_id] if d == day)

    def subject_on_day(self, class_id: str, subject_id: str, day: int) -> int:
        """عدد حصص مادة لفصل في يوم"""
        return self._subject_class_day.get((subject_id, class_id, day), 0)

    def teacher_consecutive_counted(self, teacher_id: str, day: int, period: int) -> int:
        """عدد الحصص المتتالية مع استثناء PE/SCI"""
        from .scheduler_constraints import CONSECUTIVE_RESET_CODES

        count = 0
        for p in range(period - 1, 0, -1):
            if not self.is_teacher_busy(teacher_id, day, p):
                break
            task = self._find_teacher_task_at(teacher_id, day, p)
            if task and task.subject_code in CONSECUTIVE_RESET_CODES:
                break
            count += 1
        for p in range(period + 1, 8):
            if not self.is_teacher_busy(teacher_id, day, p):
                break
            task = self._find_teacher_task_at(teacher_id, day, p)
            if task and task.subject_code in CONSECUTIVE_RESET_CODES:
                break
            count += 1
        return count

    def _find_teacher_task_at(self, teacher_id: str, day: int, period: int) -> Task | None:
        """إيجاد مهمة المعلم في (يوم, حصة)"""
        for task in self._cells.get((day, period), []):
            if task.teacher_id == teacher_id:
                return task
        return None

    def would_create_gap(self, teacher_id: str, day: int, period: int) -> bool:
        """هل إضافة حصة ستخلق فجوة للمعلم؟"""
        periods_today = sorted(
            p for d, p in self._teacher_periods[teacher_id] if d == day
        )
        periods_today.append(period)
        periods_today.sort()
        if len(periods_today) < 2:
            return False
        for i in range(len(periods_today) - 1):
            if periods_today[i + 1] - periods_today[i] > 2:
                return True
        return False

    def get_class_task_at(self, class_id: str, day: int, period: int) -> Task | None:
        """إيجاد مهمة الفصل في (يوم, حصة)"""
        for task in self._cells.get((day, period), []):
            if task.class_id == class_id:
                return task
        return None

    def all_entries(self) -> list[dict]:
        return self._entries

    def teacher_total_periods(self, teacher_id: str) -> int:
        return len(self._teacher_periods[teacher_id])

    # ── Backward-compatible aliases for scheduler_constraints.py ──

    def teacher_at(self, day: int, period: int) -> str | None:
        """مُهمَل — للتوافقية مع scheduler_constraints. يُرجع أول معلم فقط."""
        tasks = self._cells.get((day, period), [])
        return tasks[0].teacher_id if tasks else None

    def class_at(self, day: int, period: int) -> str | None:
        """مُهمَل — للتوافقية مع scheduler_constraints."""
        tasks = self._cells.get((day, period), [])
        return tasks[0].class_id if tasks else None

    def get_task_at(self, day: int, period: int) -> Task | None:
        """مُهمَل — للتوافقية. يُرجع أول مهمة فقط."""
        tasks = self._cells.get((day, period), [])
        return tasks[0] if tasks else None


# ══════════════════════════════════════════════════════════════
# أدوات مساعدة
# ══════════════════════════════════════════════════════════════


def _parse_grade(raw_grade) -> int:
    """تحويل grade من أي صيغة إلى رقم صحيح.

    يدعم: int, "G10", "10", "grade10", "الصف 10", إلخ.
    """
    if isinstance(raw_grade, int):
        return raw_grade
    s = str(raw_grade).strip().upper()
    # استخراج الرقم من النص
    import re
    match = re.search(r"\d+", s)
    return int(match.group()) if match else 0


def _grade_to_level(raw_grade) -> str:
    """تحويل grade إلى level_type (prep/sec/empty)."""
    g = _parse_grade(raw_grade)
    if g in (7, 8, 9):
        return "prep"
    if g in (10, 11, 12):
        return "sec"
    return ""


# ══════════════════════════════════════════════════════════════
# بناء المهام
# ══════════════════════════════════════════════════════════════


def build_tasks(school: School, academic_year: str) -> list[Task]:
    """بناء قائمة المهام من SubjectClassAssignment"""
    double_period_subjects = set(
        Subject.objects.filter(
            school=school, requires_double_period=True
        ).values_list("id", flat=True)
    )

    assignments = SubjectClassAssignment.objects.filter(
        school=school, academic_year=academic_year, is_active=True
    ).select_related("class_group", "subject", "teacher")

    tasks = []
    for a in assignments:
        if not a.teacher_id or a.teacher is None:
            continue

        level_type = _grade_to_level(a.class_group.grade)

        is_double = (
            a.subject_id in double_period_subjects
            or a.subject.code in {"ART", "TECH"}
        )

        for _ in range(a.weekly_periods):
            tasks.append(
                Task(
                    class_id=str(a.class_group_id),
                    class_name=str(a.class_group),
                    subject_id=str(a.subject_id),
                    subject_name=a.subject.name_ar,
                    subject_code=a.subject.code,
                    teacher_id=str(a.teacher_id),
                    teacher_name=a.teacher.full_name,
                    weekly_periods=a.weekly_periods,
                    requires_lab=a.requires_lab,
                    requires_double=is_double,
                    preferred_periods=a.preferred_periods or [],
                    level_type=level_type,
                )
            )
    return tasks


def sort_tasks(tasks: list[Task]) -> list[Task]:
    """ترتيب المهام: الأصعب أولاً (Most Constrained Variable)"""
    subject_teacher_count = defaultdict(set)
    teacher_load = defaultdict(int)
    class_load = defaultdict(int)

    for t in tasks:
        subject_teacher_count[t.subject_id].add(t.teacher_id)
        teacher_load[t.teacher_id] += 1
        class_load[t.class_id] += 1

    def priority(task: Task) -> tuple:
        return (
            len(subject_teacher_count[task.subject_id]),
            -teacher_load[task.teacher_id],
            -class_load[task.class_id],
            -task.weekly_periods,
            -int(task.requires_lab),
        )

    return sorted(tasks, key=priority)


# ══════════════════════════════════════════════════════════════
# فحص الخانات المتاحة
# ══════════════════════════════════════════════════════════════


def get_available_slots(
    grid: ScheduleGrid,
    task: Task,
    blocked_slots: set | None = None,
) -> list[tuple[int, int]]:
    """الخانات المتاحة — كل القيود الصلبة"""
    from .scheduler_constraints import get_max_periods_for_day

    available = []
    level_type = getattr(task, "level_type", "")
    for day in DAYS:
        max_p = get_max_periods_for_day(day, level_type)
        for period in range(1, max_p + 1):
            # القيود الأساسية: المعلم غير مشغول + الفصل غير مشغول
            if grid.is_teacher_busy(task.teacher_id, day, period):
                continue
            if grid.is_class_busy(task.class_id, day, period):
                continue
            # تفريغات المعلم
            if blocked_slots and (task.teacher_id, day, period) in blocked_slots:
                continue
            # القيود الصلبة الإضافية (متتالية + نصاب عالي)
            if is_slot_valid(grid, day, period, task):
                available.append((day, period))
    return available


def _get_available_slots_hard_only(
    grid: ScheduleGrid,
    task: Task,
    blocked_slots: set | None = None,
) -> list[tuple[int, int]]:
    """الخانات المتاحة — القيود الأساسية فقط (معلم + فصل)"""
    from .scheduler_constraints import get_max_periods_for_day

    available = []
    level_type = getattr(task, "level_type", "")
    for day in DAYS:
        max_p = get_max_periods_for_day(day, level_type)
        for period in range(1, max_p + 1):
            if grid.is_teacher_busy(task.teacher_id, day, period):
                continue
            if grid.is_class_busy(task.class_id, day, period):
                continue
            if blocked_slots and (task.teacher_id, day, period) in blocked_slots:
                continue
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


def _try_swap_placement(
    grid: ScheduleGrid,
    task: Task,
    blocked_slots: set | None,
    preferences: dict | None,
    max_attempts: int = 100,
) -> bool:
    """
    Phase 3: Swap Search — تبديل حصة لإفساح المجال.
    نبحث عن مهمة موضوعة لنفس المعلم يمكن نقلها لوقت آخر.
    """
    from .scheduler_constraints import get_max_periods_for_day

    level_type = getattr(task, "level_type", "")
    attempts = 0

    # ابحث في الأوقات التي يكون فيها الفصل فارغاً لكن المعلم مشغول
    for day in DAYS:
        max_p = get_max_periods_for_day(day, level_type)
        for period in range(1, max_p + 1):
            if attempts >= max_attempts:
                return False

            # الفصل يجب أن يكون فارغاً
            if grid.is_class_busy(task.class_id, day, period):
                continue

            # المعلم مشغول — نحتاج تبديل
            if not grid.is_teacher_busy(task.teacher_id, day, period):
                continue  # المعلم فارغ — لكن is_slot_valid قد يكون رافض (قيود إضافية)

            attempts += 1

            # إيجاد المهمة التي يُدرّسها المعلم في هذا الوقت
            existing = grid._find_teacher_task_at(task.teacher_id, day, period)
            if existing is None:
                continue

            # حاول نقل existing لوقت آخر
            grid.remove(day, period, existing)

            # هل يوجد مكان بديل لـ existing؟
            alt_slots = _get_available_slots_hard_only(grid, existing, blocked_slots)
            if alt_slots:
                alt_ranked = rank_slots(grid, existing, alt_slots, preferences)
                alt_day, alt_period, _ = alt_ranked[0]

                # هل يمكن وضع task هنا الآن؟
                if not grid.is_teacher_busy(task.teacher_id, day, period):
                    grid.place(alt_day, alt_period, existing)
                    grid.place(day, period, task)
                    return True
                else:
                    # المعلم لا يزال مشغولاً (مهمة أخرى)
                    grid.place(day, period, existing)  # أعد existing
            else:
                grid.place(day, period, existing)  # أعد existing

    return False


def _try_class_swap(grid, task, blocked_slots, preferences, max_attempts=200):
    """Phase 4: Class-Level Swap — move existing class task to free up a slot for the teacher."""
    from .scheduler_constraints import get_max_periods_for_day

    level_type = getattr(task, "level_type", "")
    attempts = 0

    for day in DAYS:
        max_p = get_max_periods_for_day(day, level_type)
        for period in range(1, max_p + 1):
            if attempts >= max_attempts:
                return False

            # Teacher must be free here
            if grid.is_teacher_busy(task.teacher_id, day, period):
                continue
            # Class must be busy (we need to swap something out)
            if not grid.is_class_busy(task.class_id, day, period):
                continue  # class is free — should have been caught in earlier phases

            if blocked_slots and (task.teacher_id, day, period) in blocked_slots:
                continue

            attempts += 1

            # Find the task occupying this class slot
            existing = grid.get_class_task_at(task.class_id, day, period)
            if existing is None:
                continue

            # Try to move existing to a different day where:
            # - existing's class is free
            # - existing's teacher is free
            grid.remove(day, period, existing)
            alt_slots = _get_available_slots_hard_only(grid, existing, blocked_slots)
            if alt_slots:
                # Pick the slot on the day with fewest existing teacher periods (balance)
                best = min(alt_slots, key=lambda dp: grid.teacher_periods_on_day(existing.teacher_id, dp[0]))
                grid.place(best[0], best[1], existing)
                # Now place our task
                if not grid.is_teacher_busy(task.teacher_id, day, period) and not grid.is_class_busy(task.class_id, day, period):
                    grid.place(day, period, task)
                    return True
                else:
                    # Undo — move existing back
                    grid.remove(best[0], best[1], existing)
                    grid.place(day, period, existing)
            else:
                grid.place(day, period, existing)

    return False


# ══════════════════════════════════════════════════════════════
# التوليد الرئيسي — Multi-Pass
# ══════════════════════════════════════════════════════════════


def generate_schedule(
    school: School,
    academic_year: str,
    user=None,
    max_backtrack: int = 500,
) -> dict:
    """
    التوليد الرئيسي — Multi-Pass Greedy

    Phase 1: Greedy مع كل القيود (صلبة + مرنة)
    Phase 2: إعادة محاولة الفاشلة مع قيود أساسية فقط
    Phase 3: Swap Search — تبديل حصص لإفساح المجال
    Phase 4: Class-Level Swap — تبديل حصة فصل لإفساح المجال
    """
    start_time = time.time()
    errors = []
    phase_stats = {"phase1": 0, "phase2": 0, "phase3": 0, "phase4": 0, "failed": 0}

    # ── 1. بناء المهام ──
    tasks = build_tasks(school, academic_year)
    if not tasks:
        return {
            "success": False,
            "errors": ["لا توجد توزيعات مواد (SubjectClassAssignment). أضف التوزيعات أولاً."],
        }

    # ── 2c. تحقق من سعة الفصول ──
    from .scheduler_constraints import get_max_periods_for_day

    class_demand = defaultdict(int)
    class_names = {}
    class_levels = {}
    for task in tasks:
        class_demand[task.class_id] += 1
        class_names[task.class_id] = task.class_name
        class_levels[task.class_id] = task.level_type

    capacity_warnings = []
    for cid, demand in class_demand.items():
        level = class_levels.get(cid, "")
        # Weekly capacity: Sun-Wed = 7 periods each, Thu = 6 (prep) or 7 (sec)
        thu_max = get_max_periods_for_day(4, level)
        weekly_capacity = 4 * 7 + thu_max  # Sun-Wed (4 days × 7) + Thu
        if demand > weekly_capacity:
            overflow = demand - weekly_capacity
            capacity_warnings.append(
                f"⚠️ {class_names[cid]}: مطلوب {demand} حصة لكن السعة {weekly_capacity} فقط "
                f"(فائض {overflow} — يجب تقليل {overflow} حصة)"
            )

    if capacity_warnings:
        for w in capacity_warnings:
            errors.append(w)

    # ── 2. تحميل التفضيلات ──
    prefs_qs = TeacherPreference.objects.filter(school=school, academic_year=academic_year)
    preferences = {}
    for p in prefs_qs:
        preferences[str(p.teacher_id)] = {
            "max_daily": p.max_daily_periods,
            "max_consecutive": p.max_consecutive,
            "free_day": p.free_day,
        }

    # ── 2b. تحميل تفريغات المعلمين ──
    exemptions_qs = TeacherExemption.objects.filter(
        school=school, academic_year=academic_year, is_active=True,
    )
    blocked_slots: set[tuple[str, int, int]] = set()
    for ex in exemptions_qs:
        tid = str(ex.teacher_id)
        if ex.exemption_type == "full_day":
            for p in range(1, 8):
                blocked_slots.add((tid, ex.day_of_week, p))
        else:
            blocked_slots.add((tid, ex.day_of_week, ex.period_number))

    # ── 3. ترتيب المهام (Most Constrained First) ──
    sorted_tasks = sort_tasks(tasks)

    # ══════════════════════════════════════════════════════
    # Phase 1: Greedy مع كل القيود
    # ══════════════════════════════════════════════════════
    grid = ScheduleGrid()
    unplaced_phase1 = []

    for task in sorted_tasks:
        available = get_available_slots(grid, task, blocked_slots)
        ranked = rank_slots(grid, task, available, preferences)
        if ranked:
            day, period, _ = ranked[0]
            grid.place(day, period, task)
            phase_stats["phase1"] += 1
        else:
            unplaced_phase1.append(task)

    logger.info(
        "Phase 1 (greedy): placed %d/%d, unplaced %d",
        phase_stats["phase1"], len(sorted_tasks), len(unplaced_phase1),
    )

    # ══════════════════════════════════════════════════════
    # Phase 2: إعادة محاولة — قيود أساسية فقط
    # ══════════════════════════════════════════════════════
    unplaced_phase2 = []

    if unplaced_phase1:
        random.shuffle(unplaced_phase1)
        for task in unplaced_phase1:
            available = _get_available_slots_hard_only(grid, task, blocked_slots)
            if available:
                ranked = rank_slots(grid, task, available, preferences)
                day, period, _ = ranked[0]
                grid.place(day, period, task)
                phase_stats["phase2"] += 1
            else:
                unplaced_phase2.append(task)

    logger.info(
        "Phase 2 (relaxed): placed %d more, still unplaced %d",
        phase_stats["phase2"], len(unplaced_phase2),
    )

    # ══════════════════════════════════════════════════════
    # Phase 3: Swap Search — تبديل حصص
    # ══════════════════════════════════════════════════════
    final_unplaced = []

    if unplaced_phase2:
        for task in unplaced_phase2:
            if _try_swap_placement(grid, task, blocked_slots, preferences):
                phase_stats["phase3"] += 1
            else:
                final_unplaced.append(task)
                errors.append(
                    f"تعذر وضع: {task.subject_name} → {task.class_name} ({task.teacher_name})"
                )
                phase_stats["failed"] += 1

    logger.info(
        "Phase 3 (swap): placed %d more, final failed %d",
        phase_stats["phase3"], phase_stats["failed"],
    )

    # ══════════════════════════════════════════════════════
    # Phase 4: Class-Level Swap
    # ══════════════════════════════════════════════════════
    if final_unplaced:
        still_failed = []
        for task in final_unplaced:
            if _try_class_swap(grid, task, blocked_slots, preferences):
                phase_stats["phase4"] = phase_stats.get("phase4", 0) + 1
                # Remove from errors
                error_msg = f"تعذر وضع: {task.subject_name} → {task.class_name} ({task.teacher_name})"
                if error_msg in errors:
                    errors.remove(error_msg)
                phase_stats["failed"] -= 1
            else:
                still_failed.append(task)
        final_unplaced = still_failed

    logger.info(
        "Phase 4 (class-swap): placed %d more, final failed %d",
        phase_stats.get("phase4", 0), phase_stats["failed"],
    )

    elapsed_ms = int((time.time() - start_time) * 1000)

    # ── حساب الجودة ──
    quality = calculate_quality_score(grid, preferences)

    # ── حفظ النتائج ──
    generation = None
    total_placed = phase_stats["phase1"] + phase_stats["phase2"] + phase_stats["phase3"] + phase_stats.get("phase4", 0)

    if total_placed > 0:
        try:
            with transaction.atomic():
                # أرشفة الجدولات السابقة
                ScheduleGeneration.objects.filter(
                    school=school, academic_year=academic_year,
                    status__in=("draft", "approved"),
                ).update(status="archived")

                # إلغاء الحصص القديمة
                ScheduleSlot.objects.filter(
                    school=school, academic_year=academic_year, is_active=True
                ).update(is_active=False)

                # تحميل أوقات الحصص
                time_config = {}
                for tc in TimeSlotConfig.objects.filter(school=school, is_break=False):
                    time_config[(tc.day_type, tc.period_number)] = (tc.start_time, tc.end_time)

                DEFAULT_TIMES = {
                    1: (dt_time(7, 10), dt_time(7, 55)),
                    2: (dt_time(8, 0), dt_time(8, 45)),
                    3: (dt_time(8, 50), dt_time(9, 35)),
                    4: (dt_time(9, 55), dt_time(10, 40)),
                    5: (dt_time(10, 45), dt_time(11, 30)),
                    6: (dt_time(11, 35), dt_time(12, 20)),
                    7: (dt_time(12, 25), dt_time(13, 10)),
                }

                def _get_time(day: int, period: int):
                    day_type = "thursday" if day == 4 else "regular"
                    result = time_config.get((day_type, period))
                    if result:
                        return result
                    result = time_config.get(("regular", period))
                    if result:
                        return result
                    return DEFAULT_TIMES.get(period, (dt_time(7, 10), dt_time(7, 55)))

                bulk = []
                for entry in grid.all_entries():
                    t = entry["task"]
                    d = entry["day"]
                    p = entry["period"]
                    start, end = _get_time(d, p)
                    bulk.append(
                        ScheduleSlot(
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
                        )
                    )
                ScheduleSlot.objects.bulk_create(bulk, ignore_conflicts=True)

                # عدد الحصص الفعلي في قاعدة البيانات (بدلاً من عدد الخوارزمية)
                actual_saved = ScheduleSlot.objects.filter(
                    school=school, academic_year=academic_year, is_active=True
                ).count()

                generation = ScheduleGeneration.objects.create(
                    school=school,
                    academic_year=academic_year,
                    generated_by=user,
                    status="draft",
                    quality_score=quality["score"],
                    hard_violations=len(errors),
                    soft_violations=quality["violations"],
                    total_slots_created=actual_saved,
                    generation_time_ms=elapsed_ms,
                    config_snapshot={
                        "total_tasks": len(tasks),
                        "phase1_placed": phase_stats["phase1"],
                        "phase2_placed": phase_stats["phase2"],
                        "phase3_placed": phase_stats["phase3"],
                        "phase4_placed": phase_stats.get("phase4", 0),
                        "failed": phase_stats["failed"],
                        "preferences_count": len(preferences),
                        "blocked_slots_count": len(blocked_slots),
                    },
                )
        except Exception as exc:
            logger.exception("فشل حفظ الجدول المولَّد: %s", exc)
            errors.append(f"فشل حفظ الجدول: {exc}")

    return {
        "success": len(errors) == 0,
        "grid": grid,
        "quality": quality,
        "generation": generation,
        "errors": errors,
        "elapsed_ms": elapsed_ms,
        "total_tasks": len(tasks),
        "phase_stats": phase_stats,
    }
