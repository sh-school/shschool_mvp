"""رصدُ يومِ شعبةٍ كاملاً بموجةٍ واحدة — لا سبعَ مرّاتٍ من الصفر.

## لِمَ موجةٌ لا سبع

خمسُ شُعبٍ × سبعُ حصصٍ = **خمسٌ وثلاثون شاشةً يوميّاً لكلّ مشرف**، و6300 في
العام. وشاشةٌ كهذه لا تُنفَّذ بعد أسبوع: يُعلَّم الكلُّ حاضراً وتموت البيانات
بلا أن يُخفق شيء.

## والسريانُ شرطُ صحّةٍ لا تخفيف

في [`absence_standing`](absence_standing.py) قاعدةٌ نافذة: يُعدّ اليومُ غياباً
بلا عذر إذا كان الطالبُ غائباً بلا عذرٍ في **كلّ** حصصه المسجَّلة ذلك اليوم،
وما دون ذلك غيابٌ **جزئيٌّ** يُعرض ولا يُحتسب. فلو رُصدت الحصّةُ الأولى وحدَها
لصار الغائبُ يوماً كاملاً «جزئيّاً» لا يبلغ عتبةَ استدعاءٍ ولا حرمان — والسياسةُ
تعدّ **أيّامَ تمدرس** لا حصصاً، وهذه القاعدةُ هي الجسر.

فالكتابةُ في **كلّ** حصص اليوم ليست تكراراً: هي ما يجعل الرقمَ صادقاً.

## وما يُكتب وما لا يُكتب

تُكتب حالةُ **كلّ** طالبٍ في **كلّ** حصّةٍ من حصص يومه — فالحاضرُ حاضرٌ في
سبعٍ والغائبُ غائبٌ في سبع. وحصصُ الشعبة تُقرأ من `Session` لذلك اليوم، فلا
يُخترع عددُها: سبعٌ من الأحد إلى الأربعاء، وستٌّ الخميس.

**وزوجُ الاختيار**: شعبةٌ قد يكون فيها درسان في خانةٍ زمنيّةٍ واحدة (12/1
الأحدَ: تكنولوجيا وفنونٌ بصريّةٌ معاً 09:35، نصفُ الشعبة هنا ونصفُها هناك).
فالحصصُ ثمانٍ والخاناتُ سبع. وتُكتب الحالةُ في الحصص **كلِّها** — فيراها
معلّما الزوج كلاهما ولا يُخفى الغيابُ عن أحدهما — ويُعرض للمشرف عددُ
**الخانات** لأنّه يرصد يومَ الطالب، ويومُ الطالب سبعُ خانات.

وأثرُ ذلك في الاحتساب محفوظ: قاعدةُ `absence_standing` تعدّ اليومَ غياباً إذا
غاب في **كلّ** حصصه المسجَّلة — وثمانٍ من ثمانٍ كسبعٍ من سبع.

**والمعلّمُ لا يرصد** — قرارُ المدير، واللوائحُ تُقرّه. والسجلُّ واحدٌ لكلّ
طالبٍ في كلّ حصّة (`unique_attendance_per_session`)، فمن يحفظ أخيراً يمحو ما
قبله: ما كتبه المشرفُ يُمحى رصدُ المعلّم تحته، وشاشةُ الحصّة القديمة لا تكتب
فوق ما رصده المشرف (`recorded_by_supervisor`). فلا «تشغيلَ موازياً» يُقارَن
على هذه البنية — وكان هذا الملفُّ يدّعيه خطأً.

## ولا حضورَ افتراضيّاً

شعبةٌ لم تُرصد وشعبةٌ كلُّها حاضرةٌ تبدوان في القاعدة سواءً — كلتاهما بلا
غياب. فيُكتب `SectionDayConfirmation` تثبيتاً صريحاً: من ثبّت، ومتى، وكم
غائباً، وفي كم حصّةً كُتبت الحالة. ومنه «شُعبي المتبقّية n/5».
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from core.models import StudentEnrollment

from .models import SectionDayConfirmation, Session, StudentAttendance

#: الحالاتُ التي يُدخلها المشرفُ في الموجة الصباحيّة. والعذرُ لا يُدخل هنا:
#: يُعتمد لاحقاً بعد وصول إثباته (مهلةُ يومين)، فلا يُخمَّن صباحاً.
MORNING_STATES = ("present", "absent", "late")

SOURCE = "supervisor"

#: من يرصد حالةَ الحضور: مشرفُ الجناح (أصيلاً أو بديلاً) والقيادةُ ومطوّرُ
#: المنصّة. **والمعلّمُ ليس منهم** — قرارُ المدير، واللوائحُ تُقرّه: الرصدُ
#: لمشرف الجناح وحدَه.
RECORDER_ROLES = (
    "admin_supervisor",
    "vice_admin",
    "vice_academic",
    "principal",
    "platform_developer",
)


def is_recorder(user) -> bool:
    return user.is_superuser or user.get_role() in RECORDER_ROLES


def recorded_by_supervisor(session, student) -> bool:
    """هل رصد المشرفُ هذا الطالبَ في هذه الحصّة؟

    السجلُّ واحدٌ لكلّ طالبٍ في كلّ حصّة (`unique_attendance_per_session`)،
    فمن يحفظ أخيراً يمحو ما قبله. وشاشةُ المعلّم القديمة تكتب الحالةَ ولا
    تلمس `source` — فلو ضغط معلّمٌ بحكم العادة لتغيّرت حالةُ الطالب وبقي
    السجلُّ منسوباً إلى المشرف: رقمٌ كاذبٌ باسم من لم يكتبه.
    """
    return StudentAttendance.objects.filter(
        session=session, student=student, source=SOURCE
    ).exists()


@dataclass(frozen=True)
class DayRecord:
    """ما وقع فعلاً — لا ما طُلب."""

    periods: int
    students: int
    present: int
    absent: int
    late: int
    written: int
    confirmation: SectionDayConfirmation | None

    @property
    def says(self) -> str:
        return (
            f"{self.students} طالباً في {self.periods} حصّة · "
            f"غياب {self.absent} · تأخّر {self.late}"
        )


def sessions_of(class_group, day: dt.date):
    """حصصُ الشعبة في هذا اليوم — تُقرأ ولا تُخترع.

    وعددُ حصص اليوم يختلف: سبعٌ من الأحد إلى الأربعاء، وستٌّ الخميس، وجناحٌ
    على جرسين شُعبُه تختلف بينها. فمن كتب سبعاً ثابتةً أخطأ يومَ الخميس.
    """
    return Session.objects.filter(class_group=class_group, date=day).order_by("start_time")


def slots_of(class_group, day: dt.date) -> int:
    """عددُ **الخانات الزمنيّة** في اليوم — لا عددُ الحصص.

    وهما يختلفان في شعبةٍ فيها زوجُ اختيار: 12/1 لها في الأحد ثماني حصصٍ
    وسبعُ خاناتٍ، لأنّ التكنولوجيا والفنونَ البصريّةَ في الخانة نفسِها —
    نصفُ الشعبة هنا ونصفُها هناك.

    والمعروضُ للمشرف خاناتٌ لا حصص: هو يرصد **يومَ الطالب**، ويومُ الطالب
    سبعُ خانات. والكتابةُ تقع في الحصص كلِّها (راجع `record_day`) — فيراها
    معلّما الزوج كلاهما، ولا يُخفى الغيابُ عن أحدهما.
    """
    return len({s.start_time for s in sessions_of(class_group, day)})


def enrolled_of(class_group):
    return (
        StudentEnrollment.objects.filter(class_group=class_group, is_active=True)
        .select_related("student")
        .order_by("student__full_name")
    )


def day_state(class_group, day: dt.date) -> dict:
    """حالةُ كلّ طالبٍ في هذا اليوم كما سجّلها المشرف — لعرض الشاشة.

    تُقرأ من أوّل حصّةٍ فيها سجلٌّ مصدرُه المشرف: السريانُ يجعل الحصصَ
    متطابقةً، فقراءةُ إحداها تكفي. وما رصده معلّمٌ لا يُعرض هنا حالةً
    للمشرف — فهو رصدُ غيره، وخلطُهما يُخفي أنّ المشرفَ لم يرصد بعد.
    """
    rows = (
        StudentAttendance.objects.filter(
            session__class_group=class_group, session__date=day, source=SOURCE
        )
        .values_list("student_id", "status", "whereabouts")
        .order_by("session__start_time")
    )
    state: dict = {}
    for student_id, status, where in rows:
        state.setdefault(student_id, {"status": status, "whereabouts": where})
    return state


@transaction.atomic
def record_day(class_group, day: dt.date, states: dict, by=None, note: str = "") -> DayRecord:
    """يكتب حالةَ كلّ طالبٍ في كلّ حصص يومه، ويثبّت الشعبة.

    `states` قاموسُ `{student_id: "absent"|"late"|"present"}` — وما لم يُذكر
    فيه **حاضر**. فالمشرفُ يلمس الغائبين وحدَهم، وهم القلّةُ في الغالب.

    ويُرجع ما وقع فعلاً: كم حصّةً وكم طالباً وكم سجلاً كُتب — فلا يُقال
    «رُصدت» وشعبةٌ بلا حصصٍ في ذلك اليوم.
    """
    periods = list(sessions_of(class_group, day))
    students = list(enrolled_of(class_group))
    if not periods or not students:
        return DayRecord(len(periods), len(students), 0, 0, 0, 0, None)

    tally = {"present": 0, "absent": 0, "late": 0}
    written = 0
    for enrollment in students:
        status = states.get(str(enrollment.student_id)) or states.get(enrollment.student_id)
        status = status if status in MORNING_STATES else "present"
        tally[status] += 1
        for session in periods:
            StudentAttendance.objects.update_or_create(
                session=session,
                student=enrollment.student,
                defaults={
                    "school": class_group.school,
                    "status": status,
                    "source": SOURCE,
                    "marked_by": by,
                },
            )
            written += 1

    confirmation, _ = SectionDayConfirmation.objects.update_or_create(
        class_group=class_group,
        date=day,
        defaults={
            "school": class_group.school,
            "confirmed_by": by,
            "present_count": tally["present"],
            "absent_count": tally["absent"],
            "late_count": tally["late"],
            "periods_written": len(periods),
            "note": note,
        },
    )
    return DayRecord(
        periods=len(periods),
        students=len(students),
        present=tally["present"],
        absent=tally["absent"],
        late=tally["late"],
        written=written,
        confirmation=confirmation,
    )


def confirmations_of(wing, day: dt.date | None = None) -> dict:
    """تثبيتاتُ شُعب الجناح في هذا اليوم: معرّفُ الشعبة → التثبيت."""
    day = day or timezone.localdate()
    return {
        c.class_group_id: c
        for c in SectionDayConfirmation.objects.filter(
            class_group__wing=wing, date=day
        ).select_related("confirmed_by")
    }
