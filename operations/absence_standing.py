"""
operations/absence_standing.py — موقف الطالب من عتبات الغياب.

يقرأ من [`absence_policy`](absence_policy.py) ولا يُقرّر شيئاً: يحسب أيام
الغياب بلا عذرٍ مقبول تراكمياً من بداية العام، ويقول أين يقف الطالب من
العتبات. والحرمان قرارٌ بشريّ يُبنى على هذا العرض لا يُشتقّ منه آلياً.

## أيام التمدرس لا الحصص

نصّ السياسة يعدّ **أيام التمدرس**، وقاعدتنا تُسجّل الحضور **بالحصّة**. والجسرُ
بينهما نصٌّ لا اجتهاد — المادة 3.4.3 (ص34): «يجب استكمال **4 حصص على الأقل**
خلال اليوم الدراسي الواحد ليُحسب حضور الطالب».

فالقاعدة هنا:

- **حضر 4 خاناتٍ فأكثر** — يومُ حضور. وما غابه فيه يُحصى «جزئيّاً» يُعرض ولا
  يُحتسب.
- **حضر أقلَّ من 4** — يومُ غياب، ولو حضر ثلاثاً ثمّ استأذن. وهو **بلا عذر** إن
  كان في غيابه حصّةٌ بلا عذر، و**بعذر** إن كانت كلُّها معذورة.
- **لم يُحسم** — إن كان ما حضره مع الخانات **غير المرصودة** يبلغ 4. فالحصّةُ
  التي لم يرصدها المشرفُ تبقى «لم تُرصد» (قرار 2026-09-13)، ولا يُبنى حرمانٌ
  على رصدٍ ناقص: يُعرض اليومُ ناقصاً ولا يُحتسب.

وكانت القاعدةُ قبلها: «غائبٌ في **كلّ** حصصه». فمن حضر حصّتين ثمّ هرب لم
يُحسب عليه يوم، والنصُّ يحسبه.

**والعدُّ بالخانة الزمنيّة لا بالحصّة**: شعبةٌ فيها زوجُ اختيار (تكنولوجيا وفنون
بصريّة في 09:35) لها حصّتان في خانةٍ واحدة، والطالبُ يحضر إحداهما. فالخاناتُ
سبعٌ والحصصُ ثمانٍ، وحضورُ الخانة مرّةً لا مرّتين.

و«الأربع» أقلُّ من خانات اليوم إن قصُر اليوم: يومٌ بثلاث خاناتٍ لا يُطلب فيه
أربع، فيُطلب حضورُها كلِّها.

## العذر

`excuse_type` عندنا أربعة: طبي، ظروف عائلية، رسمي، أخرى. والدليل التنظيمي
2026 (م 3.4.1.4) يقبل **خمسة** بقائمةٍ **مغلقة**: مرضٌ بتقريرٍ طبّيّ، ووفاةٌ
في القرابة الأولى، وظرفٌ عائليٌّ طارئٌ بكتابٍ رسميّ، وتمثيلُ الدولة في لقاءٍ
خارجيّ، ومواعيدُ المحاكم والهيئات (ومقابلاتُ الثاني عشر للعمل والجامعات).
والقائمةُ لا يزيدها اجتهاد: «تُعتبر جميع حالات الغياب غير مبرَّرة بخلاف
الغياب بعذر كما هو موضَّح أعلاه».

فأيّ عذرٍ مسجَّل يُعامَل هنا عذراً، ومطابقةُ نوعه بالسياسة ووجودُ مستنده
مسألةٌ إدارية لا حسابية. **وموضعُ تحفّظ**: نصُّ العتبة في م 3.4.1.3 يقول
«بدون عذرٍ **طبّيّ** رسميّ» أربعَ مرّات، وم 3.4.1.4 تُجيز الخمسةَ. فهل
يُسقط العتبةَ أيٌّ من الخمسة أم الطبّيُّ وحدَه؟ نقرأ القائمةَ المغلقةَ حاكمةً
— فالحسابُ هنا أرحمُ إن كان النصُّ الأوّلَ مقصوداً حرفاً، والسؤالُ لقسم
شؤون الاختبارات.
"""

from __future__ import annotations

from dataclasses import dataclass

from operations.absence_policy import (
    MIN_PERIODS_FOR_PRESENCE,
    Gate,
    band_for,
    breached,
    gates_for,
    next_gate,
)


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
    #: أيامٌ لم تُحسم: رصدُها ناقص، وما حضره مع ما لم يُرصد يبلغ الحدّ.
    incomplete_days: int = 0

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


ATTENDED = ("present", "late")


def _day_map(student, school, start, end) -> dict:
    """لكلّ يوم: خاناتُه، وما حضره منها، وما غابه بلا عذرٍ وبعذر — بالخانة الزمنيّة.

    والخاناتُ المجدولة تُقرأ من حصص شُعب الطالب ذلك اليوم، لا من سجلّاته وحدَها:
    فالخانةُ التي لم تُرصد لا سجلَّ لها، وبلا حصرها يُقرأ الرصدُ الناقصُ غياباً.
    """
    from operations.models import Session, StudentAttendance

    days: dict = {}

    def slot_of(date):
        return days.setdefault(
            date,
            {
                "scheduled": set(),
                "recorded": set(),
                "attended": set(),
                "unexcused": set(),
                "excused": set(),
            },
        )

    rows = StudentAttendance.objects.filter(
        student=student,
        school=school,
        session__date__gte=start,
        session__date__lte=end,
    ).values_list("session__date", "session__start_time", "status", "excuse_type")
    for date, start_time, status, excuse in rows:
        day = slot_of(date)
        day["scheduled"].add(start_time)
        day["recorded"].add(start_time)
        if status in ATTENDED:
            day["attended"].add(start_time)
        elif status == "absent":
            day["excused" if excuse else "unexcused"].add(start_time)

    scheduled = (
        Session.objects.filter(
            school=school,
            class_group__enrollments__student=student,
            class_group__enrollments__is_active=True,
            date__gte=start,
            date__lte=end,
        )
        .exclude(status="cancelled")
        .values_list("date", "start_time")
        .distinct()
    )
    for date, start_time in scheduled:
        slot_of(date)["scheduled"].add(start_time)

    # خانةٌ حضرها في إحدى حصّتَي الزوج حاضرةٌ ولو كُتب في الأخرى غير ذلك.
    for day in days.values():
        day["unexcused"] -= day["attended"]
        day["excused"] -= day["attended"] | day["unexcused"]
    return days


def _judge(day) -> str:
    """حكمُ اليوم: present · absent_unexcused · absent_excused · incomplete · unrecorded.

    ويومٌ لا رصدَ فيه أصلاً «لم يُرصد» — لا يُعرض على الطالب ناقصاً: عدمُ الرصد
    تقصيرُ من يرصد، ومحاسبتُه عند النائب الإداريّ لا في موقف الطالب.
    """
    if not day["recorded"]:
        return "unrecorded"
    need = min(MIN_PERIODS_FOR_PRESENCE, len(day["scheduled"]))
    attended = len(day["attended"])
    if attended >= need:
        return "present"
    unrecorded = len(day["scheduled"] - day["recorded"])
    if attended + unrecorded >= need:
        return "incomplete"
    return "absent_unexcused" if day["unexcused"] else "absent_excused"


def standing_for(student, school, grade=None, on=None, ese: bool = False) -> Standing:
    """موقف الطالب اليوم — تراكميّاً من بداية العام كما تنصّ السياسة."""
    from core.academic_calendar import academic_year_window

    window = academic_year_window(school, on)
    if window is None:
        return Standing(0, 0, 0, band_for(grade, ese), (), (), None)

    start, end = window
    today = on or _today()
    days = _day_map(student, school, start, min(end, today))

    verdicts = [(_judge(d), d) for d in days.values()]
    unexcused = sum(1 for v, _ in verdicts if v == "absent_unexcused")
    excused = sum(1 for v, _ in verdicts if v == "absent_excused")
    incomplete = sum(1 for v, _ in verdicts if v == "incomplete")
    partial = sum(1 for v, d in verdicts if v == "present" and d["unexcused"])

    return Standing(
        unexcused_days=unexcused,
        partial_days=partial,
        excused_days=excused,
        band=band_for(grade, ese),
        gates=gates_for(grade, ese),
        breached=breached(grade, unexcused, ese),
        upcoming=next_gate(grade, unexcused, ese),
        incomplete_days=incomplete,
    )


def _today():
    from django.utils import timezone

    return timezone.localdate()
