"""
operations/school_days.py — «هل يدرس الطلبةُ في هذا اليوم؟» من مصدرٍ واحد.

الأسبوعُ نصفُ الجواب: `bells.day_type_for` يعرف أنّ الجمعةَ والسبتَ عطلة، ولا يعرف أنّ
ثلاثاءً بعينه إجازةٌ رسميّة. ونصفُه الآخرُ في تقويم الوزارة (`CalendarEvent`): حدثٌ نوعُه
`break` وجمهورُه الطلبةُ أو الجميع — فإجازةُ الموظفين وحدَهم ليست إجازةَ طلبة.

كانت مهلةُ العذر تقرأ التقويم ولوحةُ مشرف الجناح لا تقرؤه، فعرضت الإجازةَ الرسميّة يومَ
دوامٍ بشُعبها كلِّها. ومن يسأل السؤالَ يسأله هنا.

وثلثٌ ثالث: أيّامُ ما قبل `students_start` — بدءُ دوام الموظفين وأسبوعُ اختبارات الدور
الثاني — ليست إجازةً في التقويم فلا يشملها `student_breaks`، وهي أحدٌ إلى خميسٌ فلا
يغلقها الأسبوعُ أيضاً. فكانت تُعدّ يومَ دوامٍ طلبةٍ خطأً: 846 جلسةً وُلِّدت لشُعب عامٍ
منتهٍ في 2026-08-23..27 قبل بدء الطلبة في 2026-08-30، كلُّها بلا حضور (فحصُ الإنتاج
2026-09-17). فصار اليومُ مغلقاً أيضاً إن سبق أوّلَ `students_start` في عامه.

## والصفّ نطاقٌ رابع — من مصدر المنصّة نفسه

إجازةٌ نطاقُها `grade_scope` غيرُ `all` تخصّ صفّاً بعينه. ولوحةُ الجناح تعرض عدّةَ صفوفٍ
معاً (جناح 3 فيه تاسعٌ وعاشر)، فإجازةٌ لصفّ واحد لا تُغلق شاشةً بلا صفٍّ واحد — فهذه
الشاشاتُ تُبقي `grade=None` (كلُّ نطاقٍ يُحسب، كما كان). أمّا مهلةُ العذر وملفُّ الغياب
فلكلّ منهما طالبٌ واحدٌ بصفٍّ واحد، فيُمرَّر عبر `student_grade` ليُضيّقا الاستعلامَ بـ
`_scope_for` — دالّةُ الوزارة نفسُها التي تُرشِّح نوافذ الاختبارات في `core.academic_calendar`.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from django.db.models import Min, QuerySet

from core.academic_calendar import _scope_for
from core.models import CalendarEvent, CustomUser, School, StudentEnrollment
from operations.bells import day_type_for

#: سببُ الإغلاق حين لا إجازةَ في التقويم — فالأسبوعُ وحدَه أغلق اليوم.
WEEKEND = "عطلةُ نهاية الأسبوع"

#: إجازةٌ في التقويم بلا بيان تبقى إجازة — ولا يُعرض سببٌ فارغ.
UNNAMED_BREAK = "إجازة"

#: قبل أوّل `students_start` في عامه — لا إجازةَ في التقويم، ولا طالبَ حضر بعد.
NOT_YET_OPEN = "لم يبدأ دوامُ الطلبة بعد"


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


def student_breaks(
    school: School, start: dt.date, end: dt.date, grade: str | None = None
) -> QuerySet[CalendarEvent]:
    """إجازاتُ الطلبة في تقويم المدرسة التي تتقاطع مع [start, end]."""
    qs = CalendarEvent.objects.filter(
        academic_year__school=school,
        event_type="break",
        audience__in=("both", "students"),
        start_date__lte=end,
        end_date__gte=start,
    )
    return _scoped(qs, grade)


def _openings(school: School, start: dt.date, end: dt.date) -> list[tuple[dt.date, dt.date]]:
    """لكلّ عامٍ يتقاطع مع [start, end]: (بدايتُه، أوّلُ `students_start` فيه).

    عامٌ فيه فصلان، فحدثا `students_start` فيه اثنان — وأوّلُهما (أغسطس) هو الحدّ:
    ما بعد بدء الفصل الثاني يبقى مفتوحاً بإجازة منتصف العام لا بهذا الحساب.
    """
    rows = (
        CalendarEvent.objects.filter(
            academic_year__school=school,
            academic_year__start_date__lte=end,
            academic_year__end_date__gte=start,
            event_type="students_start",
        )
        .values("academic_year__start_date")
        .annotate(opening=Min("start_date"))
    )
    return [(row["academic_year__start_date"], row["opening"]) for row in rows]


def _before_opening(day: dt.date, openings: list[tuple[dt.date, dt.date]]) -> bool:
    """أهذا اليومُ قبل بدء دوام الطلبة الأوّل في عامه؟"""
    return any(year_start <= day < opening for year_start, opening in openings)


@dataclass(frozen=True)
class SchoolDay:
    """يومٌ بنوعه من الأسبوع وإجازته من التقويم."""

    day: dt.date
    #: `regular` أو `thursday`، و`""` للجمعة والسبت.
    day_type: str
    #: اسمُ إجازة الطلبة التي تشمل اليوم (أو `NOT_YET_OPEN`)، و`""` إن كان يوم دوام.
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
    """اليومُ بنوعه وإجازته — باستعلامَين لا استعلامٍ لكلّ سؤال."""
    names = list(
        student_breaks(school, day, day, grade)
        .order_by("start_date")
        .values_list("name", flat=True)[:1]
    )
    holiday = (names[0].strip() or UNNAMED_BREAK) if names else ""
    if not holiday and _before_opening(day, _openings(school, day, day)):
        holiday = NOT_YET_OPEN
    return SchoolDay(day=day, day_type=day_type_for(day), holiday=holiday)


def is_school_day(school: School, day: dt.date, grade: str | None = None) -> bool:
    """يومٌ يدرس فيه الطلبة: أحدٌ إلى خميس، بعد بدء دوامهم، وليس في إجازةٍ من التقويم.

    والجمعةُ والسبتُ بلا استعلام: حلقاتُ المهلة تسأل عن أيّامٍ متتالية.
    """
    if not day_type_for(day):
        return False
    if student_breaks(school, day, day, grade).exists():
        return False
    return not _before_opening(day, _openings(school, day, day))


class SchoolDays:
    """أيّامُ الدراسة في نافذةٍ — بإجازاتها وبدءِ دوامها مقروءَين مرّةً لا يوماً يوماً."""

    def __init__(
        self, school: School, start: dt.date, end: dt.date, grade: str | None = None
    ) -> None:
        self.breaks = list(
            student_breaks(school, start, end, grade).values_list("start_date", "end_date")
        )
        self.openings = _openings(school, start, end)

    def __contains__(self, day: dt.date) -> bool:
        if not day_type_for(day):
            return False
        if any(a <= day <= b for a, b in self.breaks):
            return False
        return not _before_opening(day, self.openings)

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
