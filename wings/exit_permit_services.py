"""خدمةُ إذن خروج الطالب — الطلبُ والاعتمادُ وعدُّ الحصص (W-20261005-010).

- **الطلب**: حاملُ الجناح لشُعب أجنحته، والمعلّمُ لشُعبه (إسنادٌ فعليّ)؛ وغيرُ المخوَّل `PermitDeniedError` (تُحوَّل 404).
- **الاعتماد**: حاملُ الجناح (`wings.record_day`) لشُعبه، والنائبُ الإداريّ لأيّ شعبة (`wings_of`)؛ ولا اعتمادَ
  دون تسجيل حضور وليّ الأمر. بطاقتُه تُعرض ولا تُحفظ نسخةٌ منها ولا رقمُها (قرارُ المالك 2026-10-05).
- **الحصص**: عددُ الحصص المكتملة اليومَ لشعبة الطالب؛ وأقلُّ من الحدّ **تحذيرٌ** لا يمنع ولا يغيّر الحضور.
- كلُّ فعلٍ سطرُ `AuditLog` بالمعرّف المقنَّع وحدَه، بلا اسمٍ ولا رقم.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from core.academic_calendar import academic_year_for_school
from core.audit_repr import masked_repr
from core.capabilities import has_capability
from core.models import AuditLog, ClassGroup, CustomUser, School, StudentEnrollment
from operations.models import ExitPermit, Session, SubjectClassAssignment

from .exit_permit_form import MIN_PERIODS_FOR_ATTENDANCE
from .services import wings_of

REQUEST_CAP = "wings.exit_permit_request"
APPROVE_CAP = "wings.record_day"


class PermitDeniedError(Exception):
    """المستخدمُ ليس من أصحاب هذه الشعبة — تُترجم 404 (وجودُ الشعبة في غير جناحه ليس شأنَه)."""


class PermitError(Exception):
    """طلبٌ غيرُ صالح (سببٌ مجهول، أو اعتمادٌ دون حضور الوليّ)."""


def completed_periods(class_group: ClassGroup, day: dt.date) -> int:
    """الحصصُ المكتملة لشعبةٍ في يوم — من الجدول المنفَّذ لا من رصد الحضور."""
    return Session.objects.filter(class_group=class_group, date=day, status="completed").count()


def low_periods(permit: ExitPermit) -> bool:
    return permit.completed_periods < MIN_PERIODS_FOR_ATTENDANCE


def _in_my_wings(user: CustomUser, school: School, class_group: ClassGroup) -> bool:
    year = academic_year_for_school(school)
    return class_group.wing_id in {w.id for w in wings_of(user, school, year)}


def _may_act_on(
    user: CustomUser, school: School, class_group: ClassGroup, *, approve: bool
) -> bool:
    if has_capability(user, APPROVE_CAP) and _in_my_wings(user, school, class_group):
        return True
    if approve:
        return False
    return SubjectClassAssignment.objects.filter(
        school=school, class_group=class_group, teacher=user
    ).exists()


def may_request(user: CustomUser, school: School, class_group: ClassGroup) -> bool:
    return _may_act_on(user, school, class_group, approve=False)


def can_approve(user: CustomUser) -> bool:
    return has_capability(user, APPROVE_CAP)


def own_permit(user: CustomUser, school: School, permit_id: Any, *, approve: bool) -> ExitPermit:
    permit = (
        ExitPermit.objects.select_related("student", "class_group", "approved_by")
        .filter(pk=permit_id, school=school)
        .first()
    )
    if permit is None or not _may_act_on(user, school, permit.class_group, approve=approve):
        raise PermitDeniedError
    return permit


def current_class_of(student: CustomUser, school: School) -> ClassGroup:
    enrollment = StudentEnrollment.objects.current_of(student, school)
    if enrollment is None:
        raise PermitDeniedError
    return enrollment.class_group


@transaction.atomic
def request_permit(
    user: CustomUser,
    school: School,
    student: CustomUser,
    *,
    reason: str,
    note: str = "",
    exit_at: dt.datetime | None = None,
) -> ExitPermit:
    if not has_capability(user, REQUEST_CAP):
        raise PermitDeniedError
    class_group = current_class_of(student, school)
    if not _may_act_on(user, school, class_group, approve=False):
        raise PermitDeniedError
    if reason not in dict(ExitPermit.REASONS):
        raise PermitError("اختر سبباً من القائمة.")
    exit_at = exit_at or timezone.now()
    School.objects.select_for_update().get(pk=school.pk)
    last = ExitPermit.objects.filter(school=school).aggregate(m=Max("sequence"))["m"] or 0
    permit = ExitPermit.objects.create(
        school=school,
        student=student,
        class_group=class_group,
        sequence=last + 1,
        reason=reason,
        note=note.strip()[:200],
        exit_at=exit_at,
        completed_periods=completed_periods(class_group, timezone.localdate(exit_at)),
        requested_by=user,
    )
    AuditLog.log(
        user=user,
        action="create",
        model_name="other",
        object_id=permit.pk,
        object_repr=masked_repr(permit),
        changes={"exit_permit": "requested", "reason": reason},
        school=school,
    )
    return permit


@transaction.atomic
def approve_permit(
    user: CustomUser, school: School, permit_id: Any, *, guardian_present: bool
) -> ExitPermit:
    permit = own_permit(user, school, permit_id, approve=True)
    if permit.status == "approved":
        return permit
    if not guardian_present:
        raise PermitError("لا اعتمادَ قبل تسجيل حضور وليّ الأمر ببطاقته.")
    permit.guardian_present = True
    permit.status = "approved"
    permit.approved_by = user
    permit.approved_at = timezone.now()
    permit.save(update_fields=["guardian_present", "status", "approved_by", "approved_at"])
    AuditLog.log(
        user=user,
        action="update",
        model_name="other",
        object_id=permit.pk,
        object_repr=masked_repr(permit),
        changes={"exit_permit": "approved", "low_periods": low_periods(permit)},
        school=school,
    )
    return permit


def permits_for(user: CustomUser, school: School, day: dt.date) -> list[ExitPermit]:
    """أذوناتُ اليوم ضمن نطاق المستخدم: حاملُ الجناح لأجنحته، والمعلّمُ ما طلبه."""
    qs = ExitPermit.objects.filter(school=school, exit_at__date=day).select_related(
        "student", "class_group", "approved_by"
    )
    out = []
    for permit in qs.order_by("sequence"):
        if (
            _may_act_on(user, school, permit.class_group, approve=True)
            or permit.requested_by_id == user.id
        ):
            out.append(permit)
    return out
