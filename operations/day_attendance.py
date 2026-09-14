"""من يرصد حالةَ الحضور، وبأيّ مصدر — أساسُ كشف الحصص وشاشةِ المعلّم.

## والمعلّمُ لا يرصد

قرارُ المدير، واللوائحُ تُقرّه: الرصدُ لمشرف الجناح، أصيلاً أو بديلاً، والقيادة.
والسجلُّ واحدٌ لكلّ طالبٍ في كلّ حصّة (`unique_attendance_per_session`)، فمن يحفظ
أخيراً يمحو ما قبله — فشاشةُ الحصّة لا تكتب فوق ما رصده المشرف
(`recorded_by_supervisor`). وشُعبُ التربية الخاصّة خارجَ الأجنحة يرصدها معلّموها.

## وكانت هنا «الموجةُ الواحدة»

`record_day` كان يكتب حالةً واحدةً في حصص اليوم السبع بتثبيتٍ واحد
(`SectionDayConfirmation`). وأُزيل حين صار الرصدُ حصّةً حصّة
([`period_register`](period_register.py)): الطالبُ يغيب في الأولى ويصل في الثالثة،
ويخرج إلى العيادة في الخامسة، وحالةٌ واحدةٌ لليوم لا تحمل ذلك. وبقي نموذجُ التثبيت
اليوميّ لما سُجّل به في أيّام التجربة.
"""

from __future__ import annotations

from django.db.models import QuerySet

from core.models import ClassGroup, StudentEnrollment
from core.permissions import WING_DAY_RECORD

from .models import StudentAttendance

#: مصدرُ ما يرصده مشرفُ الجناح — ويفرّقه عمّا رصده معلّمٌ قبل القرار.
SOURCE = "supervisor"


def is_recorder(user) -> bool:
    """أهلُ الرصد: `WING_DAY_RECORD` في مركز الصلاحيّات — والمعلّمُ ليس منهم."""
    return user.is_superuser or user.get_role() in WING_DAY_RECORD


def can_record(user, session) -> bool:
    """هل يكتب هذا المستخدمُ حالةَ الحضور في هذه الحصّة؟

    شُعبُ الأجنحة يرصدها أهلُ الرصد وحدَهم. وشُعبُ التربية الخاصّة خارجَ الأجنحة
    بقرار الإدارة، ويرصدها معلّموها — فتبقى على حالها.
    """
    return is_recorder(user) or session.class_group.wing_id is None


def recorded_by_supervisor(session, student) -> bool:
    """هل رصد المشرفُ هذا الطالبَ في هذه الحصّة؟

    وشاشةُ المعلّم تكتب الحالةَ ولا تلمس `source` — فلو كتب معلّمٌ فوق رصد المشرف
    لتغيّرت حالةُ الطالب وبقي السجلُّ منسوباً إلى المشرف: رقمٌ كاذبٌ باسم من لم يكتبه.
    """
    return StudentAttendance.objects.filter(
        session=session, student=student, source=SOURCE
    ).exists()


def enrolled_of(class_group: ClassGroup) -> QuerySet[StudentEnrollment]:
    return (
        StudentEnrollment.objects.filter(class_group=class_group, is_active=True)
        .select_related("student")
        .order_by("student__full_name")
    )
