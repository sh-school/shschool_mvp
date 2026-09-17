"""
operations/school_days.py — «هل يدرس الطلبةُ في هذا اليوم؟» من مصدرٍ واحد.

الأسبوعُ نصفُ الجواب: `bells.day_type_for` يعرف أنّ الجمعةَ والسبتَ عطلة، ولا يعرف أنّ
ثلاثاءً بعينه إجازةٌ رسميّة. ونصفُه الآخرُ في تقويم الوزارة (`CalendarEvent`): حدثٌ نوعُه
`break` وجمهورُه الطلبةُ أو الجميع — فإجازةُ الموظفين وحدَهم ليست إجازةَ طلبة.

كانت مهلةُ العذر تقرأ التقويم ولوحةُ مشرف الجناح لا تقرؤه، فعرضت الإجازةَ الرسميّة يومَ
دوامٍ بشُعبها كلِّها. ومن يسأل السؤالَ يسأله هنا.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from django.db.models import QuerySet

from core.models import CalendarEvent, School
from operations.bells import day_type_for

#: سببُ الإغلاق حين لا إجازةَ في التقويم — فالأسبوعُ وحدَه أغلق اليوم.
WEEKEND = "عطلةُ نهاية الأسبوع"

#: إجازةٌ في التقويم بلا بيان تبقى إجازة — ولا يُعرض سببٌ فارغ.
UNNAMED_BREAK = "إجازة"


def student_breaks(school: School, start: dt.date, end: dt.date) -> QuerySet[CalendarEvent]:
    """إجازاتُ الطلبة في تقويم المدرسة التي تتقاطع مع [start, end]."""
    return CalendarEvent.objects.filter(
        academic_year__school=school,
        event_type="break",
        audience__in=("both", "students"),
        start_date__lte=end,
        end_date__gte=start,
    )


@dataclass(frozen=True)
class SchoolDay:
    """يومٌ بنوعه من الأسبوع وإجازته من التقويم."""

    day: dt.date
    #: `regular` أو `thursday`، و`""` للجمعة والسبت.
    day_type: str
    #: اسمُ إجازة الطلبة التي تشمل اليوم، و`""` إن لم تشمله إجازة.
    holiday: str = ""

    @property
    def is_open(self) -> bool:
        return bool(self.day_type) and not self.holiday

    @property
    def bell_day_type(self) -> str:
        """نوعُ الجرس الذي يرنّ فيه — و`""` ليومٍ لا جرسَ فيه ولو كان ثلاثاء."""
        return self.day_type if self.is_open else ""

    @property
    def closed_reason(self) -> str:
        """لماذا لا دوام: اسمُ الإجازة قبل عطلة الأسبوع — فالجمعةُ في إجازةٍ تُسمّى بها."""
        if self.holiday:
            return self.holiday
        return "" if self.day_type else WEEKEND


def school_day(school: School, day: dt.date) -> SchoolDay:
    """اليومُ بنوعه وإجازته — باستعلامٍ واحد."""
    names = list(
        student_breaks(school, day, day).order_by("start_date").values_list("name", flat=True)[:1]
    )
    holiday = (names[0].strip() or UNNAMED_BREAK) if names else ""
    return SchoolDay(day=day, day_type=day_type_for(day), holiday=holiday)


def is_school_day(school: School, day: dt.date) -> bool:
    """يومٌ يدرس فيه الطلبة: أحدٌ إلى خميس، وليس في إجازةٍ من تقويم الوزارة.

    والجمعةُ والسبتُ بلا استعلام: حلقاتُ المهلة تسأل عن أيّامٍ متتالية.
    """
    if not day_type_for(day):
        return False
    return not student_breaks(school, day, day).exists()


class SchoolDays:
    """أيّامُ الدراسة في نافذةٍ — بإجازاتها مقروءةً مرّةً واحدة لا يوماً يوماً."""

    def __init__(self, school: School, start: dt.date, end: dt.date) -> None:
        self.breaks = list(student_breaks(school, start, end).values_list("start_date", "end_date"))

    def __contains__(self, day: dt.date) -> bool:
        if not day_type_for(day):
            return False
        return not any(a <= day <= b for a, b in self.breaks)

    def step(self, day: dt.date, direction: int) -> dt.date:
        """اليومُ الدراسيُّ التالي (+1) أو السابق (-1) — بحدٍّ يمنع الدوران بلا نهاية."""
        for _ in range(60):
            day += dt.timedelta(days=direction)
            if day in self:
                return day
        return day
