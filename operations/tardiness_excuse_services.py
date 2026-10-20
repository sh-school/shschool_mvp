"""operations/tardiness_excuse_services.py — عذرُ التأخّر عن الحصّة (قرارُ المالك 2026-10-20، W-20261002-028).

- يعتمده **معلّمُ الحصّة** وحدَه، **في يوم الحصّة نفسِه** (بعده يُرفض).
- لا يعدّل سطرَ الحضور: سجلٌّ جديد (`TardinessExcuse`) يُسقط التأخّرَ من عدّادَي المرّات والدقائق
  (`tardiness.py` و`presence.py`)، وإلغاؤه (في اليوم نفسه) يُعيد التأخّرَ كما رُصد.
- لا مخالفةَ تأخّرٍ تُنشأ ولا تُعاد (الإنشاءُ أُزيل مع الشبكة القديمة، #913).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.db import transaction
from django.utils import timezone

from core.models import AuditLog, CustomUser, School
from operations.models import StudentAttendance, TardinessExcuse

REASON_MAX = 300


class TardinessExcuseError(ValueError):
    """رُفض الاعتماد أو الإلغاء — والرسالةُ للمستخدم."""


def _checked(
    school: School, by: CustomUser, attendance_id: Any, today: dt.date
) -> StudentAttendance:
    row = (
        StudentAttendance.objects.select_related("session", "student")
        .filter(pk=attendance_id, school=school)
        .first()
    )
    if row is None or row.session.teacher_id != by.pk:
        raise TardinessExcuseError("هذا التأخّرُ ليس من حصصك")
    if row.status != "late":
        raise TardinessExcuseError("الطالبُ غيرُ مرصودٍ متأخّراً في هذه الحصّة")
    if row.session.date != today:
        raise TardinessExcuseError("العذرُ يُعتمد في يوم الحصّة نفسِه فقط")
    return row


def _audit(
    by: CustomUser, school: School, action: str, row: StudentAttendance, changes: dict
) -> None:
    AuditLog.objects.create(
        user=by,
        school=school,
        action=action,
        model_name="other",
        object_id=str(row.pk),
        object_repr=f"عذرُ تأخّر: حضور {row.pk} · {row.session.date}"[:300],
        changes=changes,
    )


@transaction.atomic
def grant(
    school: School,
    by: CustomUser,
    attendance_id: Any,
    reason: str = "",
    *,
    today: dt.date | None = None,
) -> TardinessExcuse:
    """يعتمد عذرَ التأخّر لسطر حضورٍ «متأخّر» — ومكرَّرُه يُرجع القائمَ بلا تغيير."""
    row = _checked(school, by, attendance_id, today or timezone.localdate())
    excuse, created = TardinessExcuse.objects.get_or_create(
        attendance=row,
        defaults={"school": school, "granted_by": by, "reason": reason.strip()[:REASON_MAX]},
    )
    if created:
        _audit(
            by,
            school,
            "create",
            row,
            {"late_minutes": row.late_minutes, "reason": excuse.reason},
        )
    return excuse


@transaction.atomic
def revoke(
    school: School, by: CustomUser, attendance_id: Any, *, today: dt.date | None = None
) -> bool:
    """يلغي العذرَ فيعود التأخّرُ كما رُصد — لمعلّم الحصّة في يومها."""
    row = _checked(school, by, attendance_id, today or timezone.localdate())
    deleted, _ = TardinessExcuse.objects.filter(attendance=row).delete()
    if deleted:
        _audit(by, school, "delete", row, {"late_minutes": row.late_minutes})
    return bool(deleted)


def todays_lates(school: School, teacher: CustomUser, day: dt.date) -> list[StudentAttendance]:
    """متأخّرو حصص المعلّم في اليوم، ومع كلٍّ عذرُه إن وُجد (`tardiness_excuse`)."""
    return list(
        StudentAttendance.objects.filter(
            school=school, session__teacher=teacher, session__date=day, status="late"
        )
        .select_related("student", "session__subject", "session__class_group", "tardiness_excuse")
        .order_by("session__start_time", "student__full_name")
    )
