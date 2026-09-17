"""
operations/school_days.py — «هل يدرس الطلبةُ في هذا اليوم؟» من مصدرٍ واحد.

الأسبوعُ نصفُ الجواب: `bells.day_type_for` يعرف أنّ الجمعةَ والسبتَ عطلة، ولا يعرف أنّ
ثلاثاءً بعينه إجازةٌ رسميّة. ونصفُه الآخرُ في تقويم الوزارة (`CalendarEvent`): حدثٌ نوعُه
`break` وجمهورُه الطلبةُ أو الجميع — فإجازةُ الموظفين وحدَهم ليست إجازةَ طلبة.

كانت مهلةُ العذر تقرأ التقويم ولوحةُ مشرف الجناح لا تقرؤه، فعرضت الإجازةَ الرسميّة يومَ
دوامٍ بشُعبها كلِّها. ومن يسأل السؤالَ يسأله هنا.

## نطاقان من مصادر المنصّة نفسها، لا من منطقٍ جديد

- **الصفّ**: إجازةٌ نطاقُها `grade_scope` غيرُ `all` تخصّ صفّاً بعينه. ولوحةُ الجناح تعرض
  عدّةَ صفوفٍ معاً (جناح 3 فيه تاسعٌ وعاشر)، فإجازةٌ لصفّ واحد لا تُغلق شاشةً بلا صفٍّ واحد —
  فهذه الشاشاتُ تُبقي `grade=None` (كلُّ نطاقٍ يُحسب، كما كان). أمّا مهلةُ العذر وملفُّ الغياب
  فلكلّ منهما طالبٌ واحدٌ بصفٍّ واحد، فيُمرَّر عبر `student_grade` ليُضيّقا الاستعلامَ بـ
  `_scope_for` — دالّةُ الوزارة نفسُها التي تُرشِّح نوافذ الاختبارات في `core.academic_calendar`.
- **بدايةُ العام**: الأسبوعُ بين دوام الموظفين (`AcademicYear.start_date`) ودوام الطلبة
  (حدث `students_start`) لا يحمله حدثُ إجازة — فهو عامٌ لم يبدأ للطلبة، لا يومُ عطلة. ونهايةُ
  العام الصيفيّةُ لا حدثَ في التقويم يحدّها بعد؛ فهذا يبقى مفتوحاً حتى يُبذَر.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from django.db.models import Q, QuerySet

from core.academic_calendar import _scope_for
from core.models import CalendarEvent, CustomUser, School, StudentEnrollment
from operations.bells import day_type_for

#: سببُ الإغلاق حين لا إجازةَ في التقويم — فالأسبوعُ وحدَه أغلق اليوم.
WEEKEND = "عطلةُ نهاية الأسبوع"

#: إجازةٌ في التقويم بلا بيان تبقى إجازة — ولا يُعرض سببٌ فارغ.
UNNAMED_BREAK = "إجازة"

#: يظهر حين لم يبدأ دوامُ الطلبة بعدُ في عام اليوم — الأسبوعُ بعد دوام الموظفين.
NOT_STARTED = "لم يبدأ دوامُ الطلبة بعد"

#: (بداية إجازة، نهايتها، اسمُها) و(بدايةُ العام، نهايتُه، تاريخُ بدء دوام الطلبة).
_Break = tuple[dt.date, dt.date, str]
_Term = tuple[dt.date, dt.date, dt.date]


def student_grade(student: CustomUser, school: School) -> str | None:
    """صفُّ الطالب الحاليّ في هذه المدرسة — لتضييق فحص الإجازة إلى نطاقه.

    و`None` إن لم يكن مقيَّداً، فيُحسب كأيّ نطاق (سلوكُ ما قبل هذه الدالّة).
    """
    enrollment = StudentEnrollment.objects.current_of(  # type: ignore[no-untyped-call]
        student, school=school
    )
    return enrollment.class_group.grade if enrollment else None


def _scoped(qs: QuerySet, grade: str | None) -> QuerySet:
    """يضيّق استعلاماً بنطاق الصفّ إن عُرف — و`None` تعني «كلُّ نطاقٍ يُحسب»."""
    if grade is None:
        return qs
    return qs.filter(grade_scope__in=("all", _scope_for(grade)))


def _read_calendar(
    school: School, start: dt.date, end: dt.date, grade: str | None = None
) -> tuple[list[_Break], list[_Term]]:
    """إجازاتُ الطلبة وأعوامٌ ببدء دوامها في [start, end] — باستعلامٍ واحد.

    وكلاهما من `CalendarEvent` نفسِها (`break` و`students_start`)، فالجمعُ هنا استعلامٌ
    واحدٌ لا اثنان: `ensure_sessions_for_date` يستعلم عن أسبوعٍ كاملٍ مرّةً واحدة، وحارسُ
    ذلك مسجَّلٌ في `tests/test_holiday_sessions.py` (`len(calendar_reads) == 1`).
    """
    qs = CalendarEvent.objects.filter(
        academic_year__school=school, audience__in=("both", "students")
    ).filter(
        Q(event_type="break", start_date__lte=end, end_date__gte=start)
        | Q(
            event_type="students_start",
            academic_year__start_date__lte=end,
            academic_year__end_date__gte=start,
        )
    )
    rows = (
        _scoped(qs, grade)
        .order_by("start_date")
        .values_list(
            "event_type",
            "start_date",
            "end_date",
            "name",
            "academic_year__start_date",
            "academic_year__end_date",
        )
    )
    breaks: list[_Break] = []
    terms: list[_Term] = []
    for event_type, start_date, end_date, name, year_start, year_end in rows:
        if event_type == "break":
            breaks.append((start_date, end_date, name))
        else:
            terms.append((year_start, year_end, start_date))
    return breaks, terms


def _not_started_yet(day: dt.date, terms: list[_Term]) -> bool:
    """أوقع `day` قبل دوام الطلبة في عام ذلك اليوم؟ و`False` إن لم يُبذَر تقويمٌ يحدّه."""
    for year_start, year_end, term_start in terms:
        if year_start <= day <= year_end:
            return day < term_start
    return False


@dataclass(frozen=True)
class SchoolDay:
    """يومٌ بنوعه من الأسبوع وإجازته من التقويم."""

    day: dt.date
    #: `regular` أو `thursday`، و`""` للجمعة والسبت.
    day_type: str
    #: اسمُ إجازة الطلبة التي تشمل اليوم (أو `NOT_STARTED`)، و`""` إن كان يوم دوام.
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


def school_day(school: School, day: dt.date, grade: str | None = None) -> SchoolDay:
    """اليومُ بنوعه وإجازته — باستعلامٍ واحد."""
    breaks, terms = _read_calendar(school, day, day, grade)
    if breaks:
        holiday = breaks[0][2].strip() or UNNAMED_BREAK
    else:
        holiday = NOT_STARTED if _not_started_yet(day, terms) else ""
    return SchoolDay(day=day, day_type=day_type_for(day), holiday=holiday)


def is_school_day(school: School, day: dt.date, grade: str | None = None) -> bool:
    """يومٌ يدرس فيه الطلبة: أحدٌ إلى خميس، وليس في إجازةٍ من تقويم الوزارة، وبدأ دوامُ الطلبة.

    والجمعةُ والسبتُ بلا استعلام: حلقاتُ المهلة تسأل عن أيّامٍ متتالية.
    """
    if not day_type_for(day):
        return False
    breaks, terms = _read_calendar(school, day, day, grade)
    return not breaks and not _not_started_yet(day, terms)


class SchoolDays:
    """أيّامُ الدراسة في نافذةٍ — بإجازاتها وبدءِ عامها مقروءَين باستعلامٍ واحد لا يوماً يوماً."""

    def __init__(
        self, school: School, start: dt.date, end: dt.date, grade: str | None = None
    ) -> None:
        breaks, self.terms = _read_calendar(school, start, end, grade)
        self.breaks = [(start_date, end_date) for start_date, end_date, _name in breaks]

    def __contains__(self, day: dt.date) -> bool:
        if not day_type_for(day):
            return False
        if any(a <= day <= b for a, b in self.breaks):
            return False
        return not _not_started_yet(day, self.terms)

    def step(self, day: dt.date, direction: int) -> dt.date:
        """اليومُ الدراسيُّ التالي (+1) أو السابق (-1) — بحدٍّ يمنع الدوران بلا نهاية."""
        for _ in range(60):
            day += dt.timedelta(days=direction)
            if day in self:
                return day
        return day

    def grace_after(self, back: dt.date, days: int) -> dt.date:
        """اليومُ الدراسيُّ بعد `days` من الأيّام الدراسيّة منذ `back` — قاعدةُ المهلة الواحدة.

        كانت `excuses._grace_after` تُعيد هذه الحلقةَ بنفسها، تستعلم عن كلّ يومٍ على حدة.
        """
        day = back
        for _ in range(days):
            day = self.step(day, +1)
        return day
