"""
operations/day_summary.py — مُجمِّعُ يومِ المدرسة للوحة المدير (W-20261008-004، قرارات D-249م وD-251م وD-257م).

**أرقامٌ لا أسماء** (D-171م): الطالبُ يُعدّ **مرّةً واحدة** مهما تعدّدت صفوفُ حضوره، وحكمُه اليوميُّ هو `_judge` من
[`absence_standing`](absence_standing.py) نفسُه — لا حكمَ ثانياً يفترق عنه. فالعدّادُ في اللوحة هو ما يحسبه موقفُ الطالب وعدُّ الحرمان.

الاستعلاماتُ ثابتةٌ مهما كثر الطلاب (حارسُها `tests/test_day_summary.py`):
  ١ خاناتُ الشعب اليوم مع جناحها · ٢ تسجيلُ الطلاب النشط · ٣ صفوفُ الحضور اليوم · ٤ تثبيتاتُ الحصص اليوم ·
  ٥ إدخالاتُ الجدول المعلَّقة وغيرُها (رأسُ الإدخال) · ٦ ملخّصُ الخروج `DailyExitTally`.

القرارات في الكود:
- **14:00 بتوقيت الدوحة ثابتةٌ** (`FINAL_HOUR`): قبلها «غائبون عن أوّل خانتين» ولا يُسمّى «غائب اليوم»؛ وبعدها حكمُ السياسة بخمس خانات
  منفصلة (بلا عذر · بعذر · لم يُحسم · غير مرصود · حاضر) — «غير مرصود» لا يُدمج في الغائب.
- **حصصُ الجدول المؤقّت** (`provisional`) تدخل **حكمَ اليوم** (ما رُصد فيها يُحسب) وتُستثنى من **عدّاد خانات الجرس** و«شعب مسجَّلة».
- **«سُجِّلت»**: الخانةُ مسجَّلةٌ إن وُجد لها تثبيتُ مشرفٍ أو صفُّ حضورٍ معتمَدٌ أو رأسُ إدخالِ جدولٍ (فمسارُ الجدول لا يكتب
  `PeriodConfirmation` — مقيس) — فلا تُقرأ من التثبيت وحدَه.
- **الخارج بإذن** (عيادة/نشاط): خانةٌ مرحليّةٌ مستقلّة بعدد الطلاب؛ لا يتغيّر `_judge` ولا `absence_standing` (D-251م، مواصفةُ full لاحقة).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from django.utils import timezone

from operations.absence_standing import ATTENDED, _judge

#: ساعةُ حسمِ اليوم بتوقيت الدوحة (قرارُ المالك D-249م: ثابتةٌ لا «آخرُ خانة»).
FINAL_HOUR = 14

#: خاناتُ «الغياب المبكّر» قبل الحسم: أوّلُ خانتين من جرس اليوم.
EARLY_SLOTS = 2

PHASE_LIVE = "live"
PHASE_FINAL = "final"
PHASE_CLOSED = "closed"

#: «أين الطالب» (`StudentAttendance.whereabouts`) بإذنٍ لا تُحسب هروباً: العيادةُ والنشاط (D-251م).
PERMITTED_WHEREABOUTS = ("clinic", "activity")


@dataclass
class DayCounts:
    """أعدادُ نطاقٍ واحد (المدرسة أو جناح) — طلابٌ مميَّزون لا صفوف."""

    students: int = 0
    present: int = 0
    absent_unexcused: int = 0
    absent_excused: int = 0
    incomplete: int = 0
    unrecorded: int = 0
    #: غائبون عن أوّل خانتين معاً (قبل الحسم).
    early_absent: int = 0
    #: طلابٌ لهم رصدُ معلّمٍ بانتظار الاعتماد (يُعدّون ولا يُحتسبون حاضرين ولا غائبين).
    pending: int = 0
    sections_total: int = 0
    sections_registered: int = 0
    #: غائبون بإذنٍ خارجَ الفصل (عيادة/نشاط) — وسمٌ مرحليٌّ لا حكم.
    away_permitted: int = 0

    def as_dict(self) -> dict[str, int]:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}


@dataclass
class DaySummary:
    day: dt.date
    phase: str
    generated_at: dt.datetime
    school: DayCounts = field(default_factory=DayCounts)
    wings: list[tuple[str, DayCounts]] = field(default_factory=list)
    #: خاناتُ الجرس (غيرُ المؤقّتة وغيرُ الملغاة): العددُ ومنتهيتُها وجاريتُها.
    bell_slots: int = 0
    slots_ended: int = 0
    slots_running: int = 0
    #: رقمُ الخانة الجارية في ترتيب الجرس (1..n) أو 0.
    current_slot: int = 0
    #: الزمنُ خارج الفصل: طلابٌ · مرّات · دقائق · وجهاتٌ، وما زال خارجاً.
    exits_students: int = 0
    exits_count: int = 0
    exits_minutes: int = 0
    exits_by_destination: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """حمولةٌ JSON بلا أسماء ولا أرقامٍ شخصيّة (حارسُها نصّيٌّ في الاختبار)."""
        return {
            "day": self.day.isoformat(),
            "phase": self.phase,
            "generated_at": self.generated_at.isoformat(),
            "school": self.school.as_dict(),
            "wings": [{"name": name, **counts.as_dict()} for name, counts in self.wings],
            "bell_slots": self.bell_slots,
            "slots_ended": self.slots_ended,
            "slots_running": self.slots_running,
            "current_slot": self.current_slot,
            "exits": {
                "students": self.exits_students,
                "count": self.exits_count,
                "minutes": self.exits_minutes,
                "by_destination": self.exits_by_destination,
            },
        }


def day_phase(school: Any, day: dt.date, now: dt.datetime) -> str:
    """`closed` ليومٍ بلا دوام · `final` من 14:00 بتوقيت الدوحة (حكمُ اليوم) · `live` قبلها."""
    from operations.school_days import is_school_day

    if not is_school_day(school, day):
        return PHASE_CLOSED
    local = timezone.localtime(now)
    return PHASE_FINAL if local.hour >= FINAL_HOUR else PHASE_LIVE


def _new_day() -> dict[str, set]:
    return {
        "scheduled": set(),
        "recorded": set(),
        "attended": set(),
        "unexcused": set(),
        "excused": set(),
    }


def school_day_summary(school: Any, day: dt.date, now: dt.datetime | None = None) -> DaySummary:
    """مُجمِّعُ يومِ المدرسة: عدّاداتُ المدرسة وأجنحتُها بالحكم نفسِه — بستّة استعلاماتٍ ثابتة."""
    from core.models.academic import StudentEnrollment
    from operations.models import (
        AttendanceEntry,
        DailyExitTally,
        PeriodConfirmation,
        Session,
        StudentAttendance,
    )

    now = now or timezone.now()
    phase = day_phase(school, day, now)
    summary = DaySummary(day=day, phase=phase, generated_at=now)
    if phase == PHASE_CLOSED:
        return summary
    local_now = timezone.localtime(now).time()

    # ١ خاناتُ الشعب اليوم (غيرُ الملغاة): المؤقّتةُ فيها تدخل الحكم لا عدّادَ الجرس.
    sessions = list(
        Session.objects.filter(school=school, date=day)
        .exclude(status="cancelled")
        .values_list(
            "class_group_id",
            "class_group__wing_id",
            "class_group__wing__name",
            "class_group__wing__order",
            "start_time",
            "end_time",
            "provisional",
        )
    )
    section_slots: dict[Any, set] = {}
    section_real_slots: dict[Any, set] = {}
    section_wing: dict[Any, Any] = {}
    wing_names: dict[Any, tuple[int, str]] = {}
    bell: dict[dt.time, dt.time] = {}
    for section, wing_id, wing_name, wing_order, start, end, provisional in sessions:
        section_slots.setdefault(section, set()).add(start)
        section_wing[section] = wing_id
        if wing_id is not None:
            wing_names[wing_id] = (wing_order or 0, wing_name or "")
        if not provisional:
            section_real_slots.setdefault(section, set()).add(start)
            bell.setdefault(start, end)

    ordered_bell = sorted(bell)
    summary.bell_slots = len(ordered_bell)
    for number, start in enumerate(ordered_bell, start=1):
        end = bell[start]
        if end <= local_now:
            summary.slots_ended += 1
        elif start <= local_now:
            summary.slots_running += 1
            summary.current_slot = number
    early = set(ordered_bell[:EARLY_SLOTS])

    # ٢ تسجيلُ الطلاب النشط في شعب اليوم.
    section_ids = list(section_slots)
    enrollments = list(
        StudentEnrollment.objects.filter(
            is_active=True, class_group_id__in=section_ids
        ).values_list("student_id", "class_group_id")
    )

    # ٣ صفوفُ الحضور اليوم (طالبٌ، شعبةٌ، بدء، حالة، عذر).
    days: dict[Any, dict[str, set]] = {}
    registered: set[tuple[Any, dt.time]] = set()
    away_students: set[Any] = set()
    for student, section, start, status, excuse, where in StudentAttendance.objects.filter(
        school=school, session__date=day
    ).values_list(
        "student_id",
        "session__class_group_id",
        "session__start_time",
        "status",
        "excuse_type",
        "whereabouts",
    ):
        entry = days.setdefault(student, _new_day())
        if status == "absent" and where in PERMITTED_WHEREABOUTS:
            away_students.add(student)
        entry["recorded"].add(start)
        registered.add((section, start))
        if status in ATTENDED:
            entry["attended"].add(start)
        elif status == "absent":
            entry["excused" if excuse else "unexcused"].add(start)

    # ٤ تثبيتاتُ المشرف للحصص اليوم.
    for section, start in PeriodConfirmation.objects.filter(school=school, date=day).values_list(
        "class_group_id", "start_time"
    ):
        registered.add((section, start))

    # ٥ رؤوسُ إدخالات الجدول اليوم: المعلَّقُ (بلا قرار) يُعدّ ولا يُحتسب، وكلُّها تُسجِّل الخانة.
    pending_students: set[Any] = set()
    for student, section, start, decision in AttendanceEntry.objects.filter(
        school=school, session__date=day, superseded_by__isnull=True
    ).values_list("student_id", "session__class_group_id", "session__start_time", "decision__id"):
        registered.add((section, start))
        if decision is None:
            pending_students.add(student)

    now_slots = {start for start, end in bell.items() if end <= local_now}

    per_scope: dict[Any, DayCounts] = {}
    school_counts = summary.school

    def counts_for(wing_id: Any) -> DayCounts:
        return per_scope.setdefault(wing_id, DayCounts())

    # الشعبُ: Y = ذاتُ حصةٍ غيرِ مؤقّتة؛ X = كلُّ خاناتها المنتهية مسجَّلة.
    for section, real in section_real_slots.items():
        wing_counts = counts_for(section_wing.get(section))
        wing_counts.sections_total += 1
        school_counts.sections_total += 1
        ended = {start for start in real if start in now_slots}
        if all((section, start) in registered for start in ended):
            wing_counts.sections_registered += 1
            school_counts.sections_registered += 1

    seen: set[Any] = set()
    for student, section in enrollments:
        if student in seen:
            continue
        seen.add(student)
        wing_counts = counts_for(section_wing.get(section))
        entry = days.get(student) or _new_day()
        entry["scheduled"] |= section_slots.get(section, set())
        verdict = _judge(entry)
        for scope in (wing_counts, school_counts):
            scope.students += 1
            if verdict == "present":
                scope.present += 1
            elif verdict == "absent_unexcused":
                scope.absent_unexcused += 1
            elif verdict == "absent_excused":
                scope.absent_excused += 1
            elif verdict == "incomplete":
                scope.incomplete += 1
            else:
                scope.unrecorded += 1
            if early and early <= (entry["unexcused"] | entry["excused"]):
                scope.early_absent += 1
            if student in pending_students:
                scope.pending += 1
            if student in away_students:
                scope.away_permitted += 1

    # ٦ الزمنُ خارج الفصل — استعلامٌ واحد على الملخّص اليوميّ، مجمَّعٌ في الذاكرة.
    enrolled_ids = {student for student, _ in enrollments}
    exits_students: set[Any] = set()
    by_destination: dict[str, int] = {}
    for student, count, seconds, destinations in DailyExitTally.objects.filter(
        school=school, date=day
    ).values_list("student_id", "exit_count", "total_seconds", "by_destination"):
        if student not in enrolled_ids or not count:
            continue
        exits_students.add(student)
        summary.exits_count += count
        summary.exits_minutes += round(seconds / 60)
        for destination, detail in (destinations or {}).items():
            by_destination[destination] = by_destination.get(destination, 0) + int(
                (detail or {}).get("count", 0)
            )
    summary.exits_students = len(exits_students)
    summary.exits_by_destination = by_destination
    # الأجنحةُ بترتيبها ثمّ «بلا جناح» آخراً.
    for wing_id, (_, name) in sorted(wing_names.items(), key=lambda item: (item[1][0], item[1][1])):
        if wing_id in per_scope:
            summary.wings.append((name, per_scope[wing_id]))
    if None in per_scope:
        summary.wings.append(("بلا جناح", per_scope[None]))
    return summary
