"""طلباتُ الأولياء وشكاواهم — الانتقالُ بين المراحل وتسجيلُ المنفِّذ والتاريخ (W-20261001-019).

المسارُ للطلب والشكوى وإفادة الطالب (01 و02 و08):
    مقدَّم ← محوَّل للموظّف المختصّ ← تغذيةٌ راجعة ← تأكيدُ التواصل مع وليّ الأمر ← مغلق
وطلبُ تغيير رقم التواصل (05): مقدَّم ← يدقّقه النائبُ الإداريّ فيُطبَّق الرقمُ ويُغلق، أو يُرفض.
والخطُّ الساخن (06) سجلُّ مكالمةٍ: مقدَّم ← مغلق بعد المتابعة.

كلُّ انتقالٍ ذرّيّ، ويكتب حدثاً في `GuardianRequestEvent` وأثراً في `AuditLog` بلا اسمٍ ولا رقم.
وتغييرُ جوّال الطالب لا يمرّ من شاشة التعديل مباشرةً: `hold_phone_change` يحوّله إلى طلبٍ يدقّقه النائب.
"""

from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from core.capabilities import has_capability
from core.models.audit import AuditLog

from .guardian_request_models import GuardianRequest, GuardianRequestEvent

VERIFY_CAPABILITY = "student_affairs.verify_contact"


class TransitionError(ValueError):
    """انتقالٌ لا يسمح به مسارُ الطلب — رسالتُه تُعرض كما هي."""


def _record(req: GuardianRequest, actor, stage: str, note: str = "") -> None:
    """حدثٌ في المسار وأثرٌ في سجلّ التدقيق — كلاهما بلا اسمٍ شخصيّ."""
    GuardianRequestEvent.objects.create(request=req, stage=stage, actor=actor, note=note[:300])
    AuditLog.log(
        user=actor,
        action="update",
        model_name="other",
        object_id=req.pk,
        object_repr=str(req),
        changes={"event": f"guardian_request.{stage}", "kind": req.kind},
        school=req.school,
    )


def _require_stage(req: GuardianRequest, *allowed: str) -> None:
    if req.stage not in allowed:
        raise TransitionError("لا يُتاح هذا الإجراء في المرحلة الحالية للطلب.")


def _require_kind(req: GuardianRequest, *kinds: str) -> None:
    if req.kind not in kinds:
        raise TransitionError("هذا الإجراء لا ينطبق على هذا النوع من الطلبات.")


def _same_school(req: GuardianRequest, actor) -> None:
    membership = actor.active_membership
    if membership is None or membership.school_id != req.school_id:
        raise PermissionDenied


@transaction.atomic
def create_request(school, actor, *, kind: str, **fields) -> GuardianRequest:
    """يُنشئ طلباً في مرحلة «مقدَّم». الجوّالاتُ تُمرَّر بأسمائها (`contact_phone`…) وتُخزَّن مشفَّرةً."""
    if kind not in dict(GuardianRequest.KIND_CHOICES):
        raise TransitionError("نوعُ الطلب غير معروف.")
    phones = {
        k: fields.pop(k) for k in ("contact_phone", "current_phone", "new_phone") if k in fields
    }
    req = GuardianRequest(
        school=school,
        kind=kind,
        created_by=actor,
        updated_by=actor,
        request_date=fields.pop("request_date", None) or timezone.localdate(),
        **fields,
    )
    for name, value in phones.items():
        setattr(req, name, value)
    req.save()
    _record(req, actor, GuardianRequest.STAGE_SUBMITTED)
    return req


@transaction.atomic
def refer(req: GuardianRequest, actor, employee, on=None) -> GuardianRequest:
    """تحويلُ الطلب للموظّف المختصّ — من «مقدَّم» فقط."""
    _same_school(req, actor)
    _require_kind(req, *GuardianRequest.FOLLOW_UP_KINDS)
    _require_stage(req, GuardianRequest.STAGE_SUBMITTED)
    membership = employee.active_membership
    if membership is None or membership.school_id != req.school_id:
        raise TransitionError("الموظّف المختصّ ليس من كادر هذه المدرسة.")
    req.referred_to = employee
    req.referred_at = on or timezone.localdate()
    req.stage = GuardianRequest.STAGE_REFERRED
    req.updated_by = actor
    req.save()
    _record(req, actor, req.stage)
    return req


@transaction.atomic
def record_feedback(req: GuardianRequest, actor, text: str, on=None) -> GuardianRequest:
    """التغذيةُ الراجعة من الموظّف المختصّ — من «محوَّل» فقط، ويُسجَّل موقِّعُها وتاريخُها."""
    _same_school(req, actor)
    _require_kind(req, *GuardianRequest.FOLLOW_UP_KINDS)
    _require_stage(req, GuardianRequest.STAGE_REFERRED)
    if not (text or "").strip():
        raise TransitionError("نصُّ التغذية الراجعة مطلوب.")
    req.feedback_text = text.strip()
    req.feedback_at = on or timezone.localdate()
    req.feedback_by = actor
    req.stage = GuardianRequest.STAGE_FEEDBACK
    req.updated_by = actor
    req.save()
    _record(req, actor, req.stage)
    return req


@transaction.atomic
def confirm_contact(req: GuardianRequest, actor, status: str, on=None) -> GuardianRequest:
    """تأكيدُ التواصل مع وليّ الأمر (تمّ / لم يتمّ) — بعد التغذية الراجعة فقط."""
    _same_school(req, actor)
    _require_kind(req, *GuardianRequest.FOLLOW_UP_KINDS)
    _require_stage(req, GuardianRequest.STAGE_FEEDBACK)
    if status not in dict(GuardianRequest.CONTACT_CHOICES):
        raise TransitionError("حالةُ التواصل غير معروفة.")
    req.contact_status = status
    req.contact_at = on or timezone.localdate()
    req.stage = GuardianRequest.STAGE_CONTACT_CONFIRMED
    req.updated_by = actor
    req.save()
    _record(req, actor, req.stage, note=status)
    return req


@transaction.atomic
def close(req: GuardianRequest, actor) -> GuardianRequest:
    """إغلاقُ الطلب: بعد تأكيد التواصل (01 و02 و08)، أو مباشرةً لسجلّ الخطّ الساخن بعد المتابعة."""
    _same_school(req, actor)
    _require_kind(req, *GuardianRequest.FOLLOW_UP_KINDS, GuardianRequest.KIND_HOTLINE)
    if req.kind == GuardianRequest.KIND_HOTLINE:
        _require_stage(req, GuardianRequest.STAGE_SUBMITTED)
    else:
        _require_stage(req, GuardianRequest.STAGE_CONTACT_CONFIRMED)
    req.stage = GuardianRequest.STAGE_CLOSED
    req.closed_at = timezone.now()
    req.updated_by = actor
    req.save()
    _record(req, actor, req.stage)
    return req


def _digits(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def hold_phone_change(student, school, actor, new_phone: str) -> str:
    """يُرجع الجوّالَ الذي يبقى على سجلّ الطالب — تغييرُه طلبٌ لا تعديلٌ مباشر.

    إن اختلف الرقمُ الجديدُ عن الحالي فُتح طلبُ تغيير رقم التواصل (05) ليدقّقه النائبُ الإداريّ،
    ولا يُفتح ثانيةً ما دام طلبٌ بالرقم نفسه معلَّقاً (الاستدعاءُ المتكرّر لا يُكرّر الطلب).
    """
    current = student.get_phone_decrypted()
    if _digits(new_phone) == _digits(current):
        return current
    pending = GuardianRequest.objects.filter(
        school=school,
        student=student,
        kind=GuardianRequest.KIND_CONTACT_CHANGE,
        stage=GuardianRequest.STAGE_SUBMITTED,
    )
    if not any(_digits(r.new_phone) == _digits(new_phone) for r in pending):
        create_request(
            school,
            actor,
            kind=GuardianRequest.KIND_CONTACT_CHANGE,
            student=student,
            current_phone=current,
            new_phone=new_phone,
        )
    return current


@transaction.atomic
def verify_contact_change(req: GuardianRequest, actor, *, approve: bool) -> GuardianRequest:
    """تدقيقُ النائب الإداريّ لطلب تغيير الرقم: يُطبَّق الرقمُ عند القبول ويُسجَّل المدقِّق والتاريخ.

    القدرةُ تُفحص هنا لا في الشاشة وحدَها، ولا يدقّق الطلبَ من أنشأه (عينان لا عين).
    """
    if not has_capability(actor, VERIFY_CAPABILITY):
        raise PermissionDenied
    _same_school(req, actor)
    _require_kind(req, GuardianRequest.KIND_CONTACT_CHANGE)
    _require_stage(req, GuardianRequest.STAGE_SUBMITTED)
    if req.created_by_id and req.created_by_id == actor.pk:
        raise TransitionError("لا يدقّق الطلبَ من أنشأه — يدقّقه النائبُ الإداريّ أو المدير.")
    now = timezone.now()
    req.verified_by = actor
    req.verified_at = now
    req.updated_by = actor
    if approve:
        student = req.student
        if student is None:
            raise TransitionError("لا طالبَ مرتبطٌ بالطلب فلا يُطبَّق الرقم.")
        student.phone = req.new_phone
        student.save(update_fields=["phone"])
        req.applied_at = now
        req.stage = GuardianRequest.STAGE_CLOSED
        req.closed_at = now
    else:
        req.stage = GuardianRequest.STAGE_REJECTED
        req.closed_at = now
    req.save()
    _record(req, actor, req.stage)
    return req
