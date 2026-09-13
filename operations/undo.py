"""التراجعُ عن إدخالٍ خاطئ — نقرةُ معلّمٍ على طالبٍ آخر، أو رصدُ مشرفٍ لغير من قصد.

طلبُ المستخدم (2026-09-13): «يجب أن يكون هنالك آلية للتراجع». والقاعدةُ هنا:

- **لا شيءَ يُمحى صامتاً.** كلُّ تراجعٍ يكتب سطراً في `AuditLog`: من تراجع، وعن ماذا،
  ولماذا، وما كان قبله — فالأصلُ يبقى مقروءاً وإن زال من الرصد.
- **المعلّمُ يتراجع عن نقرته وحدَها** ما دام المشرفُ لم يثبّت (مصدرُها `teacher_late` أو
  `ClassExit` مفتوح). وبعد التثبيت صار السجلُّ للمشرف، وتصحيحُه بإعادة التثبيت.
- **المشرفُ والنائبُ يحذفان حدثاً من ملف الطالب** (غياب/تأخّر/خروج) بسبب — ويزول معه
  ما أنشأه آليّاً (مخالفةُ تأخّرٍ أو هروب) عبر إعادة حكم الكشف على اليوم.
"""

from __future__ import annotations

from django.db import transaction

from core.models import AuditLog
from operations.models import ClassExit, StudentAttendance


def _audit(request, *, action, model_name, obj, repr_, changes):
    AuditLog.objects.create(
        user=request.user,
        school=request.user.get_school(),
        action=action,
        model_name=model_name,
        object_id=str(getattr(obj, "pk", obj)),
        object_repr=repr_[:300],
        changes=changes,
        ip_address=request.META.get("REMOTE_ADDR"),
    )


@transaction.atomic
def undo_late_tap(request, session, student) -> bool:
    """المعلّمُ يتراجع عن «دخل الآن» — ما لم يثبّت المشرف."""
    row = StudentAttendance.objects.filter(
        session=session, student=student, source="teacher_late"
    ).first()
    if row is None:
        return False
    _audit(
        request,
        action="delete",
        model_name="other",
        obj=row,
        repr_=f"تراجعٌ عن «دخل الآن» — {student.full_name} · {session}",
        changes={"late_minutes": row.late_minutes, "source": row.source, "by": "teacher_undo"},
    )
    row.delete()
    return True


@transaction.atomic
def cancel_exit(request, session, student) -> bool:
    """المعلّمُ يلغي «خرج بإذن» المفتوحَ — نقرةٌ على طالبٍ آخر؛ لا أثرَ لها في الدقائق."""
    current = ClassExit.objects.filter(
        session=session, student=student, returned_at__isnull=True
    ).first()
    if current is None:
        return False
    _audit(
        request,
        action="delete",
        model_name="other",
        obj=current,
        repr_=f"إلغاءُ «خرج بإذن» — {student.full_name} · {session}",
        changes={"destination": current.destination, "left_at": current.left_at.isoformat()},
    )
    current.delete()
    return True


@transaction.atomic
def delete_attendance_event(request, row: StudentAttendance, reason: str) -> None:
    """حذفُ سجلّ حضورٍ من ملف الطالب (المشرف/النائب) بسبب — ويُعاد حكمُ الكشف على يومه.

    الحذفُ يُرجع الخانةَ «لم تُرصد» لا «حاضراً»: إن كان الرصدُ لطالبٍ آخر خطأً فالحقيقةُ أنّ
    هذا الطالبَ لم يُرصد. وإعادةُ الحكم تُزيل مخالفةَ التأخّر أو الهروب التي بُنيت عليه.
    """
    from operations.period_register import _sync_rule, sync_escapes

    session = row.session
    student = row.student
    _audit(
        request,
        action="delete",
        model_name="other",
        obj=row,
        repr_=f"حذفُ سجلّ حضور — {student.full_name} · {session}",
        changes={
            "status": row.status,
            "source": row.source,
            "late_minutes": row.late_minutes,
            "whereabouts": row.whereabouts,
            "excuse_type": row.excuse_type,
            "reason": reason,
        },
    )
    row.delete()
    # ما أنشأه الرصدُ آليّاً على هذه الحصّة يزول معه.
    _sync_rule(session.school, student, "period_tardy", set(), {}, request.user, scope=[session])
    sync_escapes(session.class_group, session.date, request.user)


@transaction.atomic
def delete_exit_event(request, exit_: ClassExit, reason: str) -> None:
    """حذفُ خروجٍ من ملف الطالب بسبب."""
    _audit(
        request,
        action="delete",
        model_name="other",
        obj=exit_,
        repr_=f"حذفُ خروجٍ من الفصل — {exit_.student.full_name} · {exit_.session}",
        changes={
            "destination": exit_.destination,
            "left_at": exit_.left_at.isoformat(),
            "returned_at": exit_.returned_at.isoformat() if exit_.returned_at else None,
            "reason": reason,
        },
    )
    exit_.delete()
