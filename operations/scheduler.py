"""
scheduler.py — خوارزمية التوليد الذكية للجدول الأسبوعي
Multi-Pass Greedy + Conflict-Aware Backtracking
مدرسة الشحانية — قطر 2025-2026
═══════════════════════════════════════════════════════════
v2: إعادة كتابة كاملة — 3 مراحل بدلاً من 1:
  Phase 1: Greedy مع كل القيود (صلبة + مرنة)
  Phase 2: إعادة محاولة الفاشلة مع قيود صلبة فقط
  Phase 3: Swap Search — تبديل حصص موضوعة لإفساح المجال
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
    """شبكة الجدول: 5 أيام × 7 حصص"""

    def __init__(self):
        self._grid: dict[int, dict[int, Task | None]] = {}
        self._teacher_slots: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self._class_slots: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self._subject_class_day: dict[tuple[str, str, int], int] = defaultdict(int)
        self._entries: list[dict] = []

        for d in DAYS:
            self._grid[d] = {}
            for p in range(1, 8):
                self._grid[d][p] = None

    def place(self, day: int, period: int, task: Task):
        self._grid[day][period] = task
        self._teacher_slots[task.teacher_id].append((day, period))
        self._class_slots[task.class_id].append((day, period))
        self._subject_class_day[(task.subject_id, task.class_id, day)] += 1
        self._entries.append({"day": day, "period": period, "task": task})

    def remove(self, day: int, period: int):
        task = self._grid[day][period]
        if task is None:
            return
        self._grid[day][period] = None
        self._teacher_slots[task.teacher_id].remove((day, period))
        self._class_slots[task.class_id].remove((day, period))
        key = (task.subject_id, task.class_id, day)
        self._subject_class_day[key] -= 1
        self._entries = [
            e for e in self._entries if not (e["day"] == day and e["period"] == period)
        ]

    def teacher_at(self, day: int, period: int) -> str | None:
        t = self._grid.get(day, {}).get(period)
        return t.teacher_id if t else None

    def class_at(self, day: int, period: int) -> str | None:
        t = self._grid.get(day, {}).get(period)
        return t.class_id if t else None

    def teacher_periods_on_day(self, teacher_id: str, day: int) -> int:
        return sum(1 for d, p in self._teacher_slots[teacher_id] if d == day)

    def class_periods_on_day(self, class_id: str, day: int) -> int:
        return sum(1 for d, p in self._class_slots[class_id] if d == day)

    def subject_on_day(self, class_id: str, subject_id: str, day: int) -> int:
        return self._subject_class_day.get((subject_id, class_id, day), 0)

    def teacher_consecutive_at(self, teacher_id: str, day: int, period: int) -> int:
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

    def teacher_consecutive_counted(self, teacher_id: str, day: int, period: int) -> int:
        from .scheduler_constraints import CONSECUTIVE_RESET_CODES

        count = 0
        for p in range(period - 1, 0, -1):
            task = self.get_task_at(day, p)
            if task is None or task.teacher_id != teacher_id:
                break
            if task.subject_code in CONSECUTIVE_RESET_CODES:
                break
            count += 1
        for p in range(period + 1, 8):
            task = self.get_task_at(day, p)
            if task is None or task.teacher_id != teacher_id:
                break
            if task.subject_code in CONSECUTIVE_RESET_CODES:
                break
            count += 1
        return count

    def would_create_gap(self, teacher_id: str, day: int, period: int) -> bool:
        periods_today = sorted(p for d, p in self._teacher_slots[teacher_id] if d == day)
        periods_today.append(period)
        periods_today.sort()
        if len(periods_today) < 2:
            return False
        for i in range(len(periods_today) - 1):
            diff = periods_today[i + 1] - periods_today[i]
            if diff > 2:
                return True
        return False

    def all_entries(self) -> list[dict]:
        return self._entries

    def get_task_at(self, day: int, period: int) -> Task | None:
        return self._grid.get(day, {}).get(period)

    def teacher_total_periods(self, teacher_id: str) -> int:
        return len(self._teacher_slots[teacher_id])

    def find_teacher_slots(self, teacher_id: str) -> list[tuple[int, int]]:
        """كل الخانات الموضوع فيها هذا المعلم"""
        return list(self._teacher_slots[teacher_id])


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

        grade = a.class_group.grade
        if grade in (7, 8, 9):
            level_type = "prep"
        elif grade in (10, 11, 12):
            level_type = "sec"
        else:
            level_type = ""

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
    # حساب عدد المعلمين الفريدين لكل مادة
    subject_teacher_count = defaultdict(set)
    # حساب حمل كل معلم
    teacher_load = defaultdict(int)
    # حساب حمل كل فصل
    class_load = defaultdict(int)

    for t in tasks:
        subject_teacher_count[t.subject_id].add(t.teacher_id)
        teacher_load[t.teacher_id] += 1
        class_load[t.class_id] += 1

    def priority(task: Task) -> tuple:
        # الأكثر تقييداً أولاً:
        return (
            len(subject_teacher_count[task.subject_id]),  # معلم وحيد أولاً
            -teacher_load[task.teacher_id],  # المعلم الأكثر حملاً أولاً
            -class_load[task.class_id],  # الفصل الأكثر حملاً أولاً
            -task.weekly_periods,  # نصاب أعلى أولاً
            -int(task.requires_lab),  # المعامل أولاً
        )

    return sorted(tasks, key=priority)


# ══════════════════════════════════════════════════════════════
# التوليد الرئيسي — Multi-Pass
# ══════════════════════════════════════════════════════════════


def _get_available_slots_hard_only(
    grid: ScheduleGrid,
    task: Task,
    blocked_slots: set | None = None,
) -> list[tuple[int, int]]:
    """الخانات التي تمر القيود الصلبة الأساسية فقط (teacher + class conflict)"""
    from .scheduler_constraints import get_max_periods_for_day

    available = []
    level_type = getattr(task, "level_type", "")
    for day in DAYS:
        max_p = get_max_periods_for_day(day, level_type)
        for period in range(1, max_p + 1):
            if grid.get_task_at(day, period) is not None:
                continue
            if blocked_slots and (task.teacher_id, day, period) in blocked_slots:
                continue
            # القيود الصلبة الأساسية فقط: تعارض معلم + تعارض فصل
            if grid.teacher_at(day, period) == task.teacher_id:
                continue
            if grid.class_at(day, period) == task.class_id:
                continue
            available.append((day, period))
    return available


def get_available_slots(
    grid: ScheduleGrid,
    task: Task,
    blocked_slots: set | None = None,
) -> list[tuple[int, int]]:
    """الخانات المتاحة (كل القيود الصلبة)"""
    from .scheduler_constraints import get_max_periods_for_day

    available = []
    level_type = getattr(task, "level_type", "")
    for day in DAYS:
        max_p = get_max_periods_for_day(day, level_type)
        for period in range(1, max_p + 1):
            if grid.get_task_at(day, period) is not None:
                continue
            if blocked_slots and (task.teacher_id, day, period) in blocked_slots:
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


def _try_swap_placement(
    grid: ScheduleGrid,
    task: Task,
    blocked_slots: set | None,
    preferences: dict | None,
    max_attempts: int = 50,
) -> bool:
    """
    Phase 3: Swap Search — حاول تبديل حصة موضوعة لإفساح المجال.

    إذا لا يوجد slot فارغ لـ task، نبحث عن حصة موضوعة لمعلم آخر
    يمكن نقلها لمكان آخر لتحرير الخانة.
    """
    from .scheduler_constraints import get_max_periods_for_day

    level_type = getattr(task, "level_type", "")
    attempts = 0

    for day in DAYS:
        max_p = get_max_periods_for_day(day, level_type)
        for period in range(1, max_p + 1):
            if attempts >= max_attempts:
                return False

            existing = grid.get_task_at(day, period)
            if existing is None:
                continue

            # لا يمكن نقل حصة نفس الفصل
            if existing.class_id == task.class_id:
                continue
            # لا يمكن نقل حصة نفس المعلم
            if existing.teacher_id == task.teacher_id:
                continue

            # هل يمكن وضع task في (day, period) إذا أزلنا existing؟
            # تحقق: المعلم ليس مشغولاً + الفصل ليس مشغولاً (الفصل فارغ بعد الإزالة)
            if grid.teacher_at(day, period) == task.teacher_id:
                continue  # المعلم مشغول بفصل آخر في هذا الوقت
            # الفصل: existing.class_id سيُزال، لكن هل task.class_id مشغول؟
            if task.class_id != existing.class_id and grid.class_at(day, period) == task.class_id:
                continue

            attempts += 1

            # أزل existing مؤقتاً
            grid.remove(day, period)

            # هل يمكن وضع task هنا الآن؟
            if is_slot_valid(grid, day, period, task):
                # هل يمكن إيجاد مكان آخر لـ existing؟
                alt_slots = get_available_slots(grid, existing, blocked_slots)
                if alt_slots:
                    alt_ranked = rank_slots(grid, existing, alt_slots, preferences)
                    alt_day, alt_period, _ = alt_ranked[0]
                    # نجح التبديل!
                    grid.place(day, period, task)
                    grid.place(alt_day, alt_period, existing)
                    return True

            # أعد existing لمكانه
            grid.place(day, period, existing)

    return False


def generate_schedule(
    school: School,
    academic_year: str,
    user=None,
    max_backtrack: int = 500,
) -> dict:
    """
    التوليد الرئيسي — Multi-Pass Greedy

    Phase 1: Greedy مع كل القيود (صلبة + مرنة)
    Phase 2: إعادة محاولة الفاشلة مع قيود صلبة فقط (بدون مرنة)
    Phase 3: Swap Search — تبديل حصص لإفساح المجال
    """
    start_time = time.time()
    errors = []
    phase_stats = {"phase1": 0, "phase2": 0, "phase3": 0, "failed": 0}

    # ── 1. بناء المهام ──
    tasks = build_tasks(school, academic_year)
    if not tasks:
        return {
            "success": False,
            "errors": ["لا توجد توزيعات مواد (SubjectClassAssignment). أضف التوزيعات أولاً."],
        }

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
    blocked_slots: set[tuple[str, int, int | None]] = set()
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
    # Phase 2: إعادة محاولة الفاشلة — قيود صلبة أساسية فقط
    # (بدون HC5 consecutive + HC6 high_weekly)
    # ══════════════════════════════════════════════════════
    unplaced_phase2 = []

    if unplaced_phase1:
        # ترتيب عشوائي خفيف لتنويع النتائج
        random.shuffle(unplaced_phase1)

        for task in unplaced_phase1:
            available = _get_available_slots_hard_only(grid, task, blocked_slots)
            if available:
                # اختر الأقل عقوبة مرنة
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
    # Phase 3: Swap Search — تبديل حصص لإفساح المجال
    # ══════════════════════════════════════════════════════
    final_unplaced = []

    if unplaced_phase2:
        for task in unplaced_phase2:
            if _try_swap_placement(grid, task, blocked_slots, preferences, max_attempts=100):
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

    elapsed_ms = int((time.time() - start_time) * 1000)

    # ── حساب الجودة ──
    quality = calculate_quality_score(grid, preferences)

    # ── حفظ النتائج ──
    generation = None
    total_placed = phase_stats["phase1"] + phase_stats["phase2"] + phase_stats["phase3"]

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

                # إنشاء الحصص الجديدة
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
                    total_slots_created=total_placed,
                    generation_time_ms=elapsed_ms,
                    config_snapshot={
                        "total_tasks": len(tasks),
                        "phase1_placed": phase_stats["phase1"],
                        "phase2_placed": phase_stats["phase2"],
                        "phase3_placed": phase_stats["phase3"],
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
