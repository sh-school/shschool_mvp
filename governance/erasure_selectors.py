"""قراءاتُ شاشة طلبات المحو (U-11 المرحلة 2 ب) — قواعدُ التوقيع كلُّها في `ErasureService`."""

from typing import Any

from django.shortcuts import get_object_or_404

from core.models import ErasureRequest, Membership
from core.models.access import ALL_STAFF_ROLES
from core.unrestricted_role import PLATFORM_DEVELOPER, has_unrestricted_role
from governance.erasure_service import ErasureService

SIGNER_ROLES = ("principal", "vice_admin")
SLOT_LABELS = {"admin": "توقيع الإدارة", "dpo": "توقيع مسؤول حماية البيانات"}
OPEN_STATUSES = ("pending", "approved")


def is_officer(user: Any, school: Any) -> bool:
    return school is not None and bool(school.data_protection_officer_id == user.pk)


def can_access(user: Any, school: Any) -> bool:
    """كالـAPI: المديرُ والنائبُ الإداريّ ومسؤولُ حماية البيانات — والمطوّرُ بصفة المسؤول وحدَها."""
    if school is None:
        return False
    if is_officer(user, school):
        return True
    if has_unrestricted_role(user):
        return False
    return bool(
        user.memberships.filter(school=school, is_active=True, role__name__in=SIGNER_ROLES).exists()
    )


def is_principal(user: Any, school: Any) -> bool:
    """من يعيّن المسؤول: المديرُ وحدَه (والخدمةُ تفرضها ثانيةً)."""
    if school is None or has_unrestricted_role(user):
        return False
    return bool(
        user.memberships.filter(school=school, is_active=True, role__name="principal").exists()
    )


def school_request(school: Any, request_id: Any) -> ErasureRequest:
    """طلبُ مدرسةٍ أخرى 404."""
    obj: ErasureRequest = get_object_or_404(ErasureRequest, pk=request_id, school=school)
    return obj


def _signatures(obj: ErasureRequest) -> list[str]:
    """«الخانةُ: الموقّعُ» — للمفتوح ما زال سارياً وحدَه، وللمنتهي ما حُفظ عليه."""
    if obj.status in OPEN_STATUSES:
        slots = ErasureService.signed_slots(obj)
    else:
        slots = {slot for slot in SLOT_LABELS if getattr(obj, f"{slot}_signed_by_id")}
    return [
        f"{label}: {getattr(obj, f'{slot}_signed_by').full_name}"
        for slot, label in SLOT_LABELS.items()
        if slot in slots
    ]


def _remaining(obj: ErasureRequest) -> list[str]:
    if obj.status not in OPEN_STATUSES:
        return []
    return [
        f"{SLOT_LABELS[slot]}: {'، '.join(u.full_name for u in users) or 'لا موقّعَ مؤهَّلاً'}"
        for slot, users in ErasureService.pending_signers(obj)
    ]


def request_rows(user: Any, school: Any) -> list[dict[str, Any]]:
    """طلباتُ المدرسة بما يعرضه القالبُ لكلٍّ منها."""
    requests = ErasureRequest.objects.filter(school=school).select_related(
        "school", "student", "requested_by", "admin_signed_by", "dpo_signed_by"
    )
    rows = []
    for obj in requests:
        can_sign, can_reject = ErasureService.signing_options(user, obj)
        remaining = _remaining(obj)
        rows.append(
            {
                "obj": obj,
                "student": obj.student.full_name if obj.student else obj.anonymized_id or "—",
                "filer": obj.requested_by.full_name if obj.requested_by else "—",
                "signed": _signatures(obj),
                "remaining": remaining,
                "executes_now": len(remaining) == 1,
                "can_sign": can_sign,
                "can_reject": can_reject,
            }
        )
    return rows


def officer_candidates(school: Any) -> list[tuple[str, str]]:
    """كادرُ المدرسة النشط — الشرطُ نفسُه الذي تقبله `ErasureService.assign_officer`."""
    rows = (
        Membership.objects.filter(
            school=school,
            user__is_active=True,
            is_active=True,
            role__name__in=ALL_STAFF_ROLES | {PLATFORM_DEVELOPER},
        )
        .values_list("user_id", "user__full_name")
        .order_by("user__full_name")
        .distinct()
    )
    return [(str(pk), name) for pk, name in rows]


def screen_context(user: Any, school: Any) -> dict[str, Any]:
    principal = is_principal(user, school)
    return {
        "rows": request_rows(user, school),
        "officer": school.data_protection_officer,
        "can_assign": principal,
        "candidates": officer_candidates(school) if principal else [],
    }
