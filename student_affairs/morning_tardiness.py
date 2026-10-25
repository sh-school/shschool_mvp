"""رصدُ التأخّر الصباحيّ — صفٌّ جديدٌ لا يمسّ رصداً قائماً، في حصّة الطالب الجارية، بحكم `can_write_grid` (W-20261004-022، D-201م أ٢).

كان العرضُ يكتب بنفسه: أوّلُ حصّةٍ لشعبة الطالب اليوم، فإن لم توجد فأوّلُ حصّةٍ في المدرسة (شعبةٌ ليست شعبتَه)
لغير المقيَّد بجناح؛ ثمّ يقلب أيَّ صفٍّ قائمٍ إلى «متأخّر» — فغيابٌ رصده المعلّمُ أو رصدُ مشرفٍ يُمحى بنقرة، بلا سجلّ.
وهنا ثلاثةُ قيود:

- **الحصّةُ حصّةُ شعبته الجاريةُ الآن** (D-239م ٤: «الحدثُ يُسجَّل بالحصّة الجارية وقت الضغط»)، ولا رجوعَ إلى شعبةٍ
  أخرى لأحد. ولا حصّةَ جاريةً ← لا رصد.
- **الكاتبُ من يكتب جدولَ تلك الشعبة الآن** (`can_write_grid`): القيادةُ الإداريّةُ وحاملُ الجناح ومعلّمُ الإسناد، في
  نافذة اليوم. والنائبُ الأكاديميّ يراقب ولا يرصد (D-201م ١، D-239م ١). وغيرُ المخوَّل بالشعبة 404 كما في الجدول.
- **رصدٌ قائمٌ لا يُكتب فوقه:** صفٌّ في `StudentAttendance` أو إدخالٌ في `AttendanceEntry` للطالب في الحصّة ← رفضٌ بلا
  كتابة. والتصحيحُ من جدول الشعبة بسببٍ (D-201م ٢)، لا من شاشة التأخّر.

ومصدرُ الصفّ كما كان: المقيَّدُ بجناحه «مشرفٌ عند البوّابة» (م 3.4.2.2)، وغيرُه بلا وسم.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import IntegrityError, transaction
from django.http import Http404

from core.audit_repr import masked_repr
from core.models.audit import AuditLog
from operations.attendance_policy import can_write_grid, grid_now
from operations.models import Session, StudentAttendance
from operations.models.attendance_ledger import AttendanceEntry
from operations.services.class_grid import NOT_FOUND_REASONS

if TYPE_CHECKING:
    from django.core.files.uploadedfile import UploadedFile

    from core.models import CustomUser, School
    from wings.scope import StudentScope

NO_CURRENT_SESSION = "لا حصّةَ جاريةً الآن لشعبة الطالب — يُرصد التأخّرُ في حصّته الجارية."
ALREADY_MARKED = "رُصد الطالبُ في حصّته الجارية — يُصحَّح الرصدُ من جدول الشعبة بسبب، ولا يُكتب فوقه تأخّر."

#: سببُ رفض `can_write_grid` ← نصُّ العرض. وما ليس هنا يأخذ `REFUSED`.
REFUSALS = {
    "read_only": "لك قراءةُ جدول هذه الشعبة لا الرصدُ فيه.",
    "inactive_class": "شعبةُ الطالب موقوفة — لا رصدَ فيها.",
    "before_window": "لم تُفتح نافذةُ رصد اليوم بعد.",
    "after_window": "أُغلقت نافذةُ رصد اليوم — يُصحَّح من جدول الشعبة بسبب.",
}
REFUSED = "لا يُرصد التأخّرُ الآن في هذه الحصّة."


@dataclass(frozen=True)
class TardinessOutcome:
    """صفُّ التأخّر المكتوب، أو نصُّ الرفض حين لا يُكتب شيء."""

    attendance: StudentAttendance | None = None
    refusal: str = ""


def current_session(
    school: School, student: CustomUser, scope: StudentScope, now: dt.datetime
) -> Session | None:
    """حصّةُ شعبة الطالب الجاريةُ في `now` — من شُعب قيده الفعّال، وبحدّ نطاق الكاتب."""
    clock = now.time()
    sessions = Session.objects.filter(
        school=school,
        date=now.date(),
        class_group__enrollments__student=student,
        class_group__enrollments__is_active=True,
        start_time__lte=clock,
        end_time__gt=clock,
    )
    return (
        scope.narrow_classes(sessions)
        .select_related("class_group")
        .order_by("start_time", "pk")
        .first()
    )


def _already_marked(session: Session, student: CustomUser) -> bool:
    return (
        StudentAttendance.objects.filter(session=session, student=student).exists()
        or AttendanceEntry.objects.filter(session=session, student=student).exists()
    )


def record_morning_tardiness(
    user: CustomUser,
    school: School,
    student: CustomUser,
    scope: StudentScope,
    *,
    excuse_minutes: int | None = None,
    excuse_file: UploadedFile | None = None,
    wing_label: str = "",
    ip_address: str | None = None,
    now: dt.datetime | None = None,
) -> TardinessOutcome:
    """يكتب تأخّراً صباحيّاً واحداً أو يرفض بسبب. غيرُ المخوَّل بشعبة الطالب ← `Http404`.

    `wing_label` يُلحق بنصّ التدقيق للمقيَّد بجناحه؛ والطالبُ يُسمّى في التدقيق مقنَّعاً (PDPPL).
    """
    moment = grid_now(now)  # لحظةُ الجدول نفسُها (`mark_late_now` و`exit_action`)
    session = current_session(school, student, scope, moment)
    if session is None:
        return TardinessOutcome(refusal=NO_CURRENT_SESSION)

    verdict = can_write_grid(
        user, session.class_group, session.date, period_start=session.start_time, now=moment
    )
    if not verdict:
        if verdict.reason in NOT_FOUND_REASONS:
            raise Http404
        return TardinessOutcome(refusal=REFUSALS.get(verdict.reason, REFUSED))
    if _already_marked(session, student):
        return TardinessOutcome(refusal=ALREADY_MARKED)

    values = {
        "status": "late",
        "tardiness_minutes": excuse_minutes,
        "excuse_notes": f"إذن تأخير {excuse_minutes} دقيقة" if excuse_minutes else "",
        "tardiness_recorded_at": moment,
        "marked_by": user,
    }
    if scope.is_wing_bound:
        # رصدُ المشرف عند البوّابة (م 3.4.2.2) — والمصدرُ يفصله عن نقرة المعلّم في الإحصاء.
        values.update(source="supervisor", whereabouts="gate")
    try:
        with transaction.atomic():
            attendance = StudentAttendance.objects.create(
                session=session, student=student, school=school, **values
            )
            if excuse_file:
                attendance.excuse_file = excuse_file
                attendance.save(update_fields=["excuse_file"])
            text = f"تسجيل تأخير {masked_repr(student)}"
            AuditLog.objects.create(
                user=user,
                school=school,
                action="create",
                model_name="other",
                object_id=str(attendance.pk),
                object_repr=f"{text} — {wing_label}" if wing_label else text,
                ip_address=ip_address,
            )
    except IntegrityError:
        # كتب غيرُه صفّاً للطالب في اللحظة نفسِها فاصطدم القيدُ الفريد — رصدٌ قائمٌ لا 500.
        return TardinessOutcome(refusal=ALREADY_MARKED)
    return TardinessOutcome(attendance=attendance)
