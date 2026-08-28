"""
operations/absence_standing.py — موقف الطالب من عتبات الغياب.

يقرأ من [`absence_policy`](absence_policy.py) ولا يُقرّر شيئاً: يحسب أيام
الغياب بلا عذرٍ مقبول تراكمياً من بداية العام، ويقول أين يقف الطالب من
العتبات. والحرمان قرارٌ بشريّ يُبنى على هذا العرض لا يُشتقّ منه آلياً.

## أيام التمدرس لا الحصص

نصّ السياسة يعدّ **أيام التمدرس**، وقاعدتنا تُسجّل الحضور **بالحصّة**. فيوم
الطالب المسجَّل قد يحوي سبع حصص، وغيابُه عن حصّةٍ واحدة ليس غياب يوم.

فالقاعدة هنا: يُعدّ اليومُ غياباً بلا عذر إذا كان الطالب غائباً بلا عذرٍ في
**كل** حصصه المسجَّلة ذلك اليوم. وما دون ذلك يُحصى منفصلاً بوصفه غياباً
جزئياً — يُعرض ولا يُحتسب، كي يرى الناظر الفرق بدل أن يبتلعه الرقم.

## العذر

`excuse_type` عندنا أربعة: طبي، ظروف عائلية، رسمي، أخرى. والسياسة تقبل
ثلاثة: مرضٌ بشهادةٍ حكومية معتمدة، وحادثٌ طارئ وظرفٌ قهريّ، ومهمّةٌ رسمية
بشهادةٍ من جهة العمل. فأيّ عذرٍ مسجَّل يُعامَل هنا عذراً، ومطابقةُ نوعه
بالسياسة ووجودُ مستنده مسألةٌ إدارية لا حسابية.
"""

from __future__ import annotations

from dataclasses import dataclass

from operations.absence_policy import Gate, band_for, breached, gates_for, next_gate


@dataclass(frozen=True)
class Standing:
    """موقف طالبٍ من عتبات عامه."""

    unexcused_days: int
    partial_days: int
    excused_days: int
    band: str
    gates: tuple[Gate, ...]
    breached: tuple[Gate, ...]
    upcoming: Gate | None

    @property
    def days_to_next(self) -> int | None:
        """كم يوماً يفصله عن الحرمان من الاختبار القادم."""
        if self.upcoming is None:
            return None
        return self.upcoming.max_days - self.unexcused_days

    @property
    def has_no_policy(self) -> bool:
        """الصفوف ١–٣ لها قسمٌ مستقلّ لم يُشفَّر — فلا حكم."""
        return not self.gates


def _day_map(student, school, start, end) -> dict:
    """لكل يومٍ: عدد حصصه، وكم منها غيابٌ بلا عذر، وكم بعذر."""
    from operations.models import StudentAttendance

    rows = StudentAttendance.objects.filter(
        student=student,
        school=school,
        session__date__gte=start,
        session__date__lte=end,
    ).values_list("session__date", "status", "excuse_type")

    days: dict = {}
    for date, status, excuse in rows:
        slot = days.setdefault(date, {"total": 0, "unexcused": 0, "excused": 0})
        slot["total"] += 1
        if status != "absent":
            continue
        if excuse:
            slot["excused"] += 1
        else:
            slot["unexcused"] += 1
    return days


def standing_for(student, school, grade=None, on=None) -> Standing:
    """موقف الطالب اليوم — تراكميّاً من بداية العام كما تنصّ السياسة."""
    from core.academic_calendar import academic_year_window

    window = academic_year_window(school, on)
    if window is None:
        return Standing(0, 0, 0, band_for(grade), (), (), None)

    start, end = window
    today = on or _today()
    days = _day_map(student, school, start, min(end, today))

    unexcused = sum(1 for d in days.values() if d["total"] and d["unexcused"] == d["total"])
    partial = sum(1 for d in days.values() if d["unexcused"] and d["unexcused"] < d["total"])
    excused = sum(1 for d in days.values() if d["excused"] and not d["unexcused"])

    return Standing(
        unexcused_days=unexcused,
        partial_days=partial,
        excused_days=excused,
        band=band_for(grade),
        gates=gates_for(grade),
        breached=breached(grade, unexcused),
        upcoming=next_gate(grade, unexcused),
    )


def _today():
    from django.utils import timezone

    return timezone.localdate()
