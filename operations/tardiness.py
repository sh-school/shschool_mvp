"""عدّادا التأخّر عن الحصّة — كم مرّة، وكم دقيقة — لكلّ طالبٍ ولكلّ مادّة.

## ما يُعدّ

- **مرّاتُ التأخّر**: دخولٌ بعد `PERIOD_TARDY_AFTER_MINUTES` (5 دقائق، قرارُ المدرسة)
  من بدء الحصّة. وهي التي تُنشئ المخالفةَ 1-01 ويُعدّ بها سلّمُها.
- **دقائقُ التأخّر**: مجموعُ ما ضاع من كلّ حصّةٍ رُصد فيها متأخّراً، **ولو دون
  الخمس**: الدقائقُ الثلاثُ لا تُنشئ مخالفةً لكنّها وقتٌ ضائعٌ من الدرس، وهي ما
  يُقارَن لاحقاً بالتحصيل.

## ولكلّ مادّة

التحصيلُ يُقاس بالمادّة، فالعدّادان يُحفظان بالمادّة أيضاً: طالبٌ يتأخّر عن الرياضيّات
وحدَها غيرُ طالبٍ يتأخّر عن كلّ شيء، والربطُ بالدرجات يحتاج هذا التمييز.

## والخانةُ لا الحصّة

حصّتا زوج الاختيار (تكنولوجيا وفنون في 09:35) تُكتب فيهما الحالةُ معاً، والطالبُ في
إحداهما. فالعدُّ بالخانة الزمنيّة: تأخّرٌ واحدٌ لا اثنان.

## والنافذة

فصلٌ دراسيٌّ أو عامٌ كامل — يُمرَّر المدى. والسلّمُ يُعدّ في الفصل (قرارُ المدرسة)؛
أمّا العدّادُ المعروضُ فللفصل والعام معاً.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field

from operations.absence_policy import PERIOD_TARDY_AFTER_MINUTES


def minutes_after_start(session, arrived: dt.datetime | dt.time) -> int:
    """دقائقُ ما بين بدء الحصّة والوصول — لا تنزل عن الصفر."""
    arrived_time = arrived.time() if isinstance(arrived, dt.datetime) else arrived
    start = dt.datetime.combine(session.date, session.start_time)
    at = dt.datetime.combine(session.date, arrived_time)
    return max(0, int((at - start).total_seconds() // 60))


def is_period_tardy(minutes: int | None) -> bool:
    """تأخّرٌ يُعدّ مخالفةً: بعد خمس دقائق من بدء الحصّة."""
    return minutes is not None and minutes > PERIOD_TARDY_AFTER_MINUTES


@dataclass
class SubjectTardiness:
    subject: str
    count: int = 0
    minutes: int = 0


@dataclass
class Tardiness:
    """عدّادا التأخّر لطالبٍ في مدى."""

    count: int = 0
    minutes: int = 0
    #: دخولٌ متأخّرٌ دون الحدّ — دقائقُه محسوبةٌ ولا مخالفةَ فيه.
    under_threshold: int = 0
    #: «متأخّر» بلا دقائقَ مقيسة — يُعدّ مرّةً ولا يُضاف إلى الدقائق.
    unmeasured: int = 0
    by_subject: dict[str, SubjectTardiness] = field(default_factory=dict)


def tardiness_for(student, school, start: dt.date, end: dt.date) -> Tardiness:
    """عدّادا التأخّر عن الحصص بين `start` و`end` شاملَين."""
    from operations.models import StudentAttendance

    rows = (
        StudentAttendance.objects.filter(
            student=student,
            school=school,
            status="late",
            session__date__gte=start,
            session__date__lte=end,
        )
        .values_list(
            "session__date", "session__start_time", "session__subject__name_ar", "late_minutes"
        )
        .order_by("session__date", "session__start_time")
    )

    # خانةٌ واحدةٌ لزوج الاختيار: أكبرُ الدقائق فيها، والمادّةُ أوّلُ ما سُجّل.
    slots: dict = {}
    for day, start_time, subject, minutes in rows:
        key = (day, start_time)
        current = slots.get(key)
        if current is None:
            slots[key] = [subject or "—", minutes]
        elif minutes is not None and (current[1] is None or minutes > current[1]):
            current[1] = minutes

    result = Tardiness()
    subjects: dict[str, SubjectTardiness] = defaultdict(lambda: SubjectTardiness(""))
    for subject, minutes in slots.values():
        entry = subjects[subject]
        entry.subject = subject
        if minutes is None:
            result.unmeasured += 1
            result.count += 1
            entry.count += 1
            continue
        result.minutes += minutes
        entry.minutes += minutes
        if is_period_tardy(minutes):
            result.count += 1
            entry.count += 1
        else:
            result.under_threshold += 1
    result.by_subject = dict(sorted(subjects.items(), key=lambda kv: (-kv[1].minutes, kv[0])))
    return result


def tardiness_now(student, school, on: dt.date | None = None) -> dict:
    """العدّادان للفصل الجاري وللعام الجاري — ما تعرضه صفحةُ الطالب."""
    from django.utils import timezone

    from core.academic_calendar import AcademicCalendar, academic_year_window

    day = on or timezone.localdate()
    now = AcademicCalendar.current(school, day)
    window = academic_year_window(school, day)
    semester = None
    if now.semester is not None:
        semester = tardiness_for(student, school, now.semester.start_date, day)
    year = tardiness_for(student, school, window[0], day) if window else None
    return {"semester": semester, "year": year, "semester_label": now.semester}
