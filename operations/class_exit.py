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
    return ClassExit.objects.create(
        school=session.school,
        session=session,
        student=student,
        destination=destination,
        left_at=now,
        allowed_by=by,
    )


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
