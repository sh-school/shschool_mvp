"""دقائقُ الحضور الفعليّ لكلّ طالبٍ في كلّ مادّة — ما يُقارَن بالتحصيل.

طلبُ المستخدم (2026-09-13): «أريد أن أعرف كم في كلّ مادّةٍ حضر من الدقائق»، مع حفظ
كلّ حدثٍ بتاريخه. الأحداثُ محفوظةٌ سطراً سطراً في جداولها — سجلُّ الحضور بحصّته
ومادّته وتاريخه، وخروجُ الفصل بوقتيه، والمخالفاتُ بحصّتها — وهذا الملفُّ **يجمعها
رقماً** عند الطلب ولا يخزّنه: رقمٌ مخزَّنٌ ثانيةً يخالف مصدرَه يوماً ما.

لكلّ مادّةٍ في مدى (فصلٍ أو عام):

| البند | من أين |
|---|---|
| حصصٌ مجدولة | `Session` غيرُ الملغاة لشعبة الطالب |
| دقائقُ الجدول | مجموعُ (النهاية − البداية) لتلك الحصص |
| حصصُ الغياب | `StudentAttendance.status = absent` (بعذرٍ وبدونه، ويُميَّزان) |
| مرّاتُ التأخّر ودقائقُه | `status = late` و`late_minutes` (`tardiness.py`) |
| مرّاتُ الخروج ودقائقُه | `ClassExit` (خروج ← عودة، ومن لم يعد حتى نهاية الحصّة) |
| الهروب | `BehaviorInfraction.auto_rule` in (class_escape, school_escape) بحصّته |
| **دقائقُ الحضور** | دقائقُ الجدول − دقائقُ حصص الغياب − دقائقُ التأخّر − دقائقُ الخروج |

والخانةُ لا الحصّة: زوجُ الاختيار حصّتان في توقيتٍ واحد، والطالبُ في إحداهما —
فيُعدّ بالخانة (التاريخ + وقتُ البدء) وتُنسب المادّةُ إلى أوّل حصّةٍ فيها.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field

from django.utils import timezone


@dataclass
class SubjectPresence:
    subject: str
    scheduled_periods: int = 0
    scheduled_minutes: int = 0
    absent_periods: int = 0
    absent_excused_periods: int = 0
    absent_minutes: int = 0
    late_count: int = 0
    late_minutes: int = 0
    exit_count: int = 0
    exit_minutes: int = 0
    escape_count: int = 0
    unrecorded_periods: int = 0

    @property
    def present_minutes(self) -> int:
        return max(
            0, self.scheduled_minutes - self.absent_minutes - self.late_minutes - self.exit_minutes
        )

    @property
    def present_pct(self) -> int:
        if not self.scheduled_minutes:
            return 0
        return round(self.present_minutes * 100 / self.scheduled_minutes)


@dataclass
class Presence:
    start: dt.date
    end: dt.date
    by_subject: dict[str, SubjectPresence] = field(default_factory=dict)

    @property
    def total(self) -> SubjectPresence:
        t = SubjectPresence("المجموع")
        for s in self.by_subject.values():
            for name in (
                "scheduled_periods",
                "scheduled_minutes",
                "absent_periods",
                "absent_excused_periods",
                "absent_minutes",
                "late_count",
                "late_minutes",
                "exit_count",
                "exit_minutes",
                "escape_count",
                "unrecorded_periods",
            ):
                setattr(t, name, getattr(t, name) + getattr(s, name))
        return t


def _minutes(start_time: dt.time, end_time: dt.time) -> int:
    a = dt.datetime.combine(dt.date.today(), start_time)
    b = dt.datetime.combine(dt.date.today(), end_time)
    return max(0, int((b - a).total_seconds() // 60))


def presence_for(student, school, start: dt.date, end: dt.date) -> Presence:
    """دقائقُ الحضور بالمادّة بين `start` و`end` شاملَين."""
    from behavior.models import BehaviorInfraction
    from operations.models import ClassExit, Session, StudentAttendance
    from operations.tardiness import is_period_tardy

    # 1) الخاناتُ المجدولة: (تاريخ، بدء) ← (مادّة، دقائق)
    scheduled = (
        Session.objects.filter(
            school=school,
            class_group__enrollments__student=student,
            class_group__enrollments__is_active=True,
            date__gte=start,
            date__lte=end,
        )
        .exclude(status="cancelled")
        .values_list("date", "start_time", "end_time", "subject__name_ar")
        .order_by("date", "start_time")
    )
    slots: dict = {}
    for day, st, en, subject in scheduled:
        slots.setdefault((day, st), (subject or "—", _minutes(st, en)))

    subjects: dict[str, SubjectPresence] = defaultdict(lambda: SubjectPresence(""))
    for subject, minutes in slots.values():
        entry = subjects[subject]
        entry.subject = subject
        entry.scheduled_periods += 1
        entry.scheduled_minutes += minutes

    # 2) الحضورُ المرصود بالخانة: أفضلُ حالٍ في الخانة (حاضرٌ في إحدى حصّتَي الزوج حاضر)
    rows = StudentAttendance.objects.filter(
        student=student, school=school, session__date__gte=start, session__date__lte=end
    ).values_list("session__date", "session__start_time", "status", "excuse_type", "late_minutes")
    RANK = {"present": 3, "late": 2, "excused": 1, "absent": 0}
    marks: dict = {}
    for day, st, status, excuse, minutes in rows:
        key = (day, st)
        cur = marks.get(key)
        if cur is None or RANK.get(status, 0) > RANK.get(cur[0], 0):
            marks[key] = (status, bool(excuse), minutes)
        elif (
            status == cur[0] == "late"
            and minutes is not None
            and (cur[2] is None or minutes > cur[2])
        ):
            marks[key] = (status, cur[1], minutes)

    for key, (subject, minutes) in slots.items():
        entry = subjects[subject]
        mark = marks.get(key)
        if mark is None:
            entry.unrecorded_periods += 1
            continue
        status, excused, late = mark
        if status in ("absent", "excused"):
            entry.absent_periods += 1
            entry.absent_minutes += minutes
            if excused or status == "excused":
                entry.absent_excused_periods += 1
        elif status == "late":
            if late is None or is_period_tardy(late):
                entry.late_count += 1
            entry.late_minutes += late or 0

    # 3) الخروجُ بإذنٍ: بالخانة، حتى العودة أو نهاية الحصّة
    exits = ClassExit.objects.filter(
        student=student, school=school, session__date__gte=start, session__date__lte=end
    ).select_related("session")
    for exit_ in exits:
        key = (exit_.session.date, exit_.session.start_time)
        subject = slots.get(
            key, (exit_.session.subject.name_ar if exit_.session.subject_id else "—", 0)
        )[0]
        entry = subjects[subject]
        entry.subject = subject
        entry.exit_count += 1
        until = timezone.make_aware(dt.datetime.combine(exit_.session.date, exit_.session.end_time))
        entry.exit_minutes += exit_.minutes_away(until)

    # 4) الهروب: بحصّته
    escapes = BehaviorInfraction.objects.filter(
        student=student,
        school=school,
        auto_rule__in=("class_escape", "school_escape"),
        session__date__gte=start,
        session__date__lte=end,
    ).values_list("session__date", "session__start_time")
    for key in escapes:
        subject = slots.get(tuple(key), ("—", 0))[0]
        subjects[subject].subject = subject
        subjects[subject].escape_count += 1

    ordered = dict(sorted(subjects.items(), key=lambda kv: (-kv[1].scheduled_minutes, kv[0])))
    return Presence(start=start, end=end, by_subject=ordered)


def presence_now(student, school, on: dt.date | None = None) -> dict:
    """للفصل الجاري وللعام الجاري — ما تعرضه صفحةُ الطالب."""
    from core.academic_calendar import AcademicCalendar, academic_year_window

    day = on or timezone.localdate()
    now = AcademicCalendar.current(school, day)
    window = academic_year_window(school, day)
    semester = None
    if now.semester is not None:
        semester = presence_for(student, school, now.semester.start_date, day)
    year = presence_for(student, school, window[0], day) if window else None
    return {"semester": semester, "year": year, "semester_label": now.semester}
