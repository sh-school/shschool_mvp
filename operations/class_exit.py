"""خروجُ الطالب من الفصل بإذن المعلّم — النقرتان، وما يُكتب في سجلّ الحضور.

- **«خرج بإذن»**: سطرُ `ClassExit` بلحظته ووجهته. لا يمسّ سجلَّ الحضور: الطالبُ
  حاضرٌ خرج لدقائق.
- **«عاد»**: يُغلق السطرَ بلحظة العودة.
- **من لم يعد حتى نهاية الحصّة**: عند تثبيت المشرف (أو إغلاق اليوم) يُكتب في سجلّ
  الحضور «غائب · `whereabouts` = العيادة/خرج بإذن» بمصدر `teacher_out` — فلا
  يُحسب هارباً (`AWAY_WITH_LEAVE`) ولا يُعدّ حاضراً حصّةً غاب أكثرَها.

المعلّمُ لا يُدخل وقتاً: اللحظاتُ كلُّها من النقرة (قرارُ 2026-09-13).
"""

from __future__ import annotations

import datetime as dt

from django.db import transaction
from django.utils import timezone

from operations.models import ClassExit, StudentAttendance

#: وجهاتٌ تُخرج الطالبَ من الجناح فيحتاج بطاقةَ المشرف — فيُشعَر فوراً (قرارُ 2026-09-14).
#: دورةُ المياه داخل الجناح، بلا إشعار.
NOTIFY_SUPERVISOR_FOR = ("clinic", "admin")

#: وجهةُ الخروج → «أين الطالب» في سجلّ الحضور لمن لم يعد.
WHEREABOUTS_OF = {
    "clinic": "clinic",
    "admin": "out_permit",
    "restroom": "out_permit",
    "other": "out_permit",
}
TEACHER_OUT = "teacher_out"


def open_exit(session, student) -> ClassExit | None:
    return ClassExit.objects.filter(
        session=session, student=student, returned_at__isnull=True
    ).first()


@transaction.atomic
def leave(session, student, destination: str, by, now: dt.datetime | None = None) -> ClassExit:
    """نقرةُ «خرج بإذن» — والنقرةُ الثانية على طالبٍ خارجٍ تُعيد سطرَه لا تكرّره."""
    now = now or timezone.now()
    current = open_exit(session, student)
    if current is not None:
        return current
    if destination not in dict(ClassExit.DESTINATIONS):
        destination = "other"
    exit_ = ClassExit.objects.create(
        school=session.school,
        session=session,
        student=student,
        destination=destination,
        left_at=now,
        allowed_by=by,
    )
    if destination in NOTIFY_SUPERVISOR_FOR:
        _notify_supervisor(exit_)
    return exit_


def _notify_supervisor(exit_: ClassExit) -> None:
    """يُشعِر من يحمل الجناحَ اليوم (أصيلاً أو بديلاً) — الطالبُ قادمٌ إليه لبطاقة الخروج.

    الإشعارُ لا يُسقط الخروجَ إن تعذّر: نقرةُ المعلّم حقيقةٌ تُحفظ أوّلاً.
    """
    import logging

    from django.urls import reverse

    logger = logging.getLogger(__name__)
    wing = exit_.session.class_group.wing if exit_.session.class_group.wing_id else None
    holder = wing.current_supervisor(exit_.session.date) if wing is not None else None
    if holder is None:
        return
    try:
        from notifications.hub import NotificationHub

        NotificationHub.dispatch(
            event_type="class_exit",
            school=exit_.school,
            recipients=[holder],
            title=f"خروجٌ من الفصل — {exit_.student.full_name}",
            body=(
                f"{exit_.student.full_name} ({exit_.session.class_group}) خرج إلى "
                f"{exit_.get_destination_display()} الساعة {timezone.localtime(exit_.left_at):%H:%M} "
                f"بإذن {exit_.allowed_by.full_name if exit_.allowed_by else 'المعلّم'} — "
                "يحتاج بطاقةَ خروجٍ من الجناح."
            ),
            related_url=reverse("wings:record_section", args=[exit_.session.class_group_id])
            + f"?date={exit_.session.date.isoformat()}",
            related_object_id=str(exit_.pk),
            sent_by=exit_.allowed_by,
        )
    except Exception as exc:  # noqa: BLE001 — الإشعارُ تابعٌ للحدث لا شرطٌ له
        logger.warning("class_exit: إشعارُ المشرف تعذّر [exit=%s]: %s", exit_.pk, exc)


@transaction.atomic
def come_back(session, student, now: dt.datetime | None = None) -> ClassExit | None:
    """نقرةُ «عاد» — تُغلق الخروجَ المفتوح؛ ولا شيءَ إن لم يكن خارجاً."""
    current = open_exit(session, student)
    if current is None:
        return None
    current.returned_at = now or timezone.now()
    current.save(update_fields=["returned_at"])
    return current


def session_end(session) -> dt.datetime:
    return timezone.make_aware(dt.datetime.combine(session.date, session.end_time))


@transaction.atomic
def close_unreturned(session, by=None) -> int:
    """من خرج ولم يعد حتى نهاية الحصّة: يُغلق خروجُه عند نهايتها، ويُكتب «غائب · بإذن».

    يُستدعى عند تثبيت المشرف للحصّة، ولا يكتب فوق ما رصده المشرفُ أو ما كان مكتوباً
    بمصدر المشرف — التثبيتُ سيّدُ السجلّ.
    """
    end = session_end(session)
    closed = 0
    for exit_ in ClassExit.objects.filter(
        session=session, returned_at__isnull=True, left_at__lt=end
    ):
        exit_.returned_at = end
        exit_.save(update_fields=["returned_at"])
        closed += 1
        row = StudentAttendance.objects.filter(session=session, student=exit_.student).first()
        if row is not None and row.source == "supervisor":
            continue
        StudentAttendance.objects.update_or_create(
            session=session,
            student=exit_.student,
            defaults={
                "school": session.school,
                "status": "absent",
                "source": TEACHER_OUT,
                "marked_by": by or exit_.allowed_by,
                "whereabouts": WHEREABOUTS_OF.get(exit_.destination, "out_permit"),
            },
        )
    return closed


def exits_of_session(session) -> dict:
    """`{student_id: (open_exit | None, [exits])}` لعرض الشاشة."""
    out: dict = {}
    for exit_ in ClassExit.objects.filter(session=session).order_by("left_at"):
        current, all_ = out.setdefault(exit_.student_id, [None, []])
        all_.append(exit_)
        if exit_.returned_at is None:
            out[exit_.student_id][0] = exit_
    return out
