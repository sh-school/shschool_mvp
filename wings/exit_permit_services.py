"""خدمةُ ورقة خروج الطالب — الإصدارُ المباشر وعدُّ الحصص (W-20261005-010، W-20261116-003).

- **الإصدار**: خمسةُ أدوار — مشرفُ الجناح لشُعب جناحه، ومنسّقُ شؤون الطلاب والنائبان والمدير للمدرسة كلِّها
  (`wings_of`)؛ والمعلّمُ لا يُصدر ولا يطبع وغيرُ المخوَّل `PermitDeniedError` (تُحوَّل 404). بلا اعتمادٍ في المنصّة:
  يوقّعها بالقلم النائبُ الإداريّ أو المكلَّف بعمله، وبلا حصّةٍ جاريةٍ شرطاً.
- **موافقةُ الوليّ**: حضورٌ ببطاقته (لا تُحفظ صورتُها ولا رقمُها) أو اتّصالٌ هاتفيّ برقمٍ ومتّصل؛
  ولا تُطبع ورقةٌ بلا طريقة، ولا اتّصالَ بلا رقمٍ ومتّصل.
- **الحصص**: عددُ الحصص المكتملة اليومَ لشعبة الطالب؛ وأقلُّ من الحدّ **تحذيرٌ** لا يمنع ولا يغيّر الحضور.
- كلُّ فعلٍ سطرُ `AuditLog` بالمعرّف المقنَّع، والهاتفُ مقنَّعٌ وحدَه، ولا اسمَ ولا رقمَ كاملاً.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from core.academic_calendar import academic_year_for_school
from core.audit_repr import masked_repr
from core.capabilities import has_capability
from core.models import AuditLog, ClassGroup, CustomUser, School, StudentEnrollment
from core.privacy import mask_phone
from operations.models import ExitPermit, Session
from operations.services.absence_followup import guardian_phones_for

from .exit_permit_form import MIN_PERIODS_FOR_ATTENDANCE
from .services import wings_of

REQUEST_CAP = "wings.exit_permit_request"

RESTRICTED_METHOD_MESSAGE = (
    "المادة 3.7.3.4 تحصر خروج هذا الطالب بحضور وليّ الأمر وتوقيعه؛ "
    "اختر «حضر ببطاقته» ولا يصحّ الاتّصال الهاتفيّ."
)

_PHONE_RE = re.compile(r"^\+?[0-9]{6,15}$")


class PermitDeniedError(Exception):
    """المستخدمُ ليس من أصحاب هذه الشعبة — تُترجم 404 (وجودُ الشعبة في غير جناحه ليس شأنَه)."""


class PermitError(Exception):
    """طلبٌ غيرُ صالح (سببٌ مجهول، أو طريقةُ موافقةٍ ناقصة)."""


def completed_periods(class_group: ClassGroup, day: dt.date) -> int:
    """الحصصُ المكتملة لشعبةٍ في يوم — من الجدول المنفَّذ لا من رصد الحضور."""
    return Session.objects.filter(class_group=class_group, date=day, status="completed").count()


def low_periods(permit: ExitPermit) -> bool:
    return permit.completed_periods < MIN_PERIODS_FOR_ATTENDANCE


def _my_wing_ids(user: CustomUser, school: School) -> set[Any]:
    year = academic_year_for_school(school)
    return {w.id for w in wings_of(user, school, year)}


def may_issue(user: CustomUser, school: School, class_group: ClassGroup) -> bool:
    """القدرةُ للأدوار الخمسة، والشعبةُ في نطاقه (مشرفُ الجناح: أجنحتُه؛ والباقون: المدرسةُ كلُّها)."""
    return has_capability(user, REQUEST_CAP) and class_group.wing_id in _my_wing_ids(user, school)


def is_printable(permit: ExitPermit) -> bool:
    """لا تُطبع ورقةٌ بلا طريقة موافقة؛ ومع الاتّصال بلا رقمٍ ومتّصلٍ لا تُطبع. و`approved` القديمةُ مقروءةٌ كما كانت."""
    if permit.status == "approved":
        return True
    if permit.status != "issued":
        return False
    if permit.guardian_method == "present":
        return True
    return permit.guardian_method == "phone" and bool(permit.call_phone and permit.caller_name)


def own_permit(user: CustomUser, school: School, permit_id: Any) -> ExitPermit:
    permit = (
        ExitPermit.objects.select_related("student", "class_group", "requested_by")
        .filter(pk=permit_id, school=school)
        .first()
    )
    if permit is None or not may_issue(user, school, permit.class_group):
        raise PermitDeniedError
    return permit


def current_class_of(student: CustomUser, school: School) -> ClassGroup:
    enrollment = StudentEnrollment.objects.current_of(student, school)
    if enrollment is None:
        raise PermitDeniedError
    return enrollment.class_group


def registered_phones(school: School, student: CustomUser) -> list[str]:
    """أرقامُ أولياء أمر الطالب المسجَّلة — تُقرأ وقتَ العرض ولا تُخزَّن للاختيار."""
    return guardian_phones_for(school, [student.pk]).get(student.pk, [])


def _clean_phone(raw: str) -> str:
    return re.sub(r"[\s\-]", "", raw or "")


def _guardian_fields(
    school: School,
    student: CustomUser,
    *,
    method: str,
    call_phone: str,
    caller_name: str,
    caller_relation: str,
    restricted: bool = False,
) -> dict[str, Any]:
    """حقولُ طريقة الموافقة بعد التحقّق؛ والناقصُ `PermitError` بعربيّةٍ مفهومة."""
    if method not in dict(ExitPermit.GUARDIAN_METHODS):
        raise PermitError("اختر طريقة موافقة وليّ الأمر.")
    if method == "present":
        return {"guardian_method": "present", "guardian_present": True}
    if restricted:
        raise PermitError(RESTRICTED_METHOD_MESSAGE)
    phone = _clean_phone(call_phone)
    name = caller_name.strip()[:150]
    if not phone or not name:
        raise PermitError("الاتّصال يستلزم رقم الهاتف ومن المتصل (الاسم والصلة).")
    if not _PHONE_RE.match(phone):
        raise PermitError("رقم الهاتف غير صالح.")
    known = {_clean_phone(n) for n in registered_phones(school, student)}
    return {
        "guardian_method": "phone",
        "call_phone": phone,
        "call_phone_registered": phone in known,
        "caller_name": name,
        "caller_relation": caller_relation.strip()[:40],
    }


@transaction.atomic
def issue_permit(
    user: CustomUser,
    school: School,
    student: CustomUser,
    *,
    reason: str,
    guardian_method: str,
    note: str = "",
    call_phone: str = "",
    caller_name: str = "",
    caller_relation: str = "",
    exit_at: dt.datetime | None = None,
    restricted: bool = False,
) -> ExitPermit:
    """يُصدر الورقةَ مباشرةً (بلا اعتماد، وبلا حصّةٍ جاريةٍ شرطاً)؛ والموظفُ والوقتُ يُسجَّلان تلقائيّاً.

    `restricted` جوابُ سؤال الإعاقة (قرار المالك 2026-11-17): يُستعمل للتحقّق لحظةَ الإصدار فقط، ولا يُخزَّن ولا يُسجَّل.
    """
    class_group = current_class_of(student, school)
    if not may_issue(user, school, class_group):
        raise PermitDeniedError
    if reason not in dict(ExitPermit.REASONS):
        raise PermitError("اختر سبباً من القائمة.")
    guardian = _guardian_fields(
        school,
        student,
        method=guardian_method,
        call_phone=call_phone,
        caller_name=caller_name,
        caller_relation=caller_relation,
        restricted=restricted,
    )
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
        status="issued",
        **guardian,
    )
    changes: dict[str, Any] = {
        "exit_permit": "issued",
        "reason": reason,
        "guardian_method": permit.guardian_method,
    }
    if permit.call_phone:
        changes["call_phone"] = mask_phone(permit.call_phone)
    AuditLog.log(
        user=user,
        action="create",
        model_name="other",
        object_id=permit.pk,
        object_repr=masked_repr(permit),
        changes=changes,
        school=school,
    )
    return permit


def permits_for(user: CustomUser, school: School, day: dt.date) -> list[ExitPermit]:
    """ورقاتُ اليوم ضمن نطاق المستخدم: مشرفُ الجناح لأجنحته، والأربعةُ الباقون للمدرسة كلِّها."""
    if not has_capability(user, REQUEST_CAP):
        return []
    wing_ids = _my_wing_ids(user, school)
    qs = ExitPermit.objects.filter(school=school, exit_at__date=day).select_related(
        "student", "class_group__wing", "requested_by"
    )
    return [p for p in qs.order_by("sequence") if p.class_group.wing_id in wing_ids]
