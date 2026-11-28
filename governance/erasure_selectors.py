"""قراءاتُ شاشة طلبات المحو (U-11) — القواعدُ كلُّها من `erasure_service`."""

from typing import Any

from core.models import ErasureRequest
from core.unrestricted_role import has_unrestricted_role
from governance.erasure_service import available_actions, officer_candidates, signature_state

_ADMIN_LABELS = {"principal": "المدير", "vice_admin": "النائب الإداريّ"}
_DPO_LABEL = "مسؤول حماية البيانات"
_STATUS_TONES = {"completed": "green", "rejected": "red"}


def may_enter(user: Any, school: Any) -> bool:
    """المديرُ والنائبُ الإداريّ والمسؤولُ المعيَّن — والمطوّرُ بتعيينه مسؤولاً وحدَه."""
    if school is None:
        return False
    if user.pk == school.data_protection_officer_id:
        return True
    if has_unrestricted_role(user):
        return False
    return bool(
        user.memberships.filter(
            school=school, is_active=True, role__name__in=("principal", "vice_admin")
        ).exists()
    )


def can_appoint(user: Any, school: Any) -> bool:
    """التعيينُ للمدير وحدَه — لا للمطوّر."""
    if school is None or has_unrestricted_role(user):
        return False
    return bool(
        user.memberships.filter(school=school, is_active=True, role__name="principal").exists()
    )


def _row(user: Any, obj: ErasureRequest) -> dict[str, Any]:
    state = signature_state(obj)
    labels = {
        "admin": _ADMIN_LABELS.get(state["admin_role"], state["admin_role"]),
        "dpo": _DPO_LABEL,
    }
    open_request = obj.status in ("pending", "approved")
    can_sign, can_reject = available_actions(user, obj)
    return {
        "obj": obj,
        "student": obj.student.full_name if obj.student else obj.anonymized_id or "—",
        "filer": obj.requested_by.full_name if obj.requested_by else "—",
        "tone": _STATUS_TONES.get(obj.status, ""),
        "signed": [
            (labels[slot], signer.full_name) for slot, signer in sorted(state["signed"].items())
        ]
        if open_request
        # المنتهي: ما سُجّل وقتَه، ولا يُعاد وزنُه بصفة الموقّع اليوم.
        else [
            (label, signer.full_name)
            for label, signer in (("الإدارة", obj.admin_signed_by), (_DPO_LABEL, obj.dpo_signed_by))
            if signer is not None
        ],
        "missing": [labels[slot] for slot in state["missing"]] if open_request else [],
        "can_sign": can_sign,
        "can_reject": can_reject,
    }


def erasure_page(user: Any, school: Any) -> dict[str, Any]:
    """سياقُ الشاشة دفعةً واحدة: طلباتُ المدرسة، والمسؤولُ المعيَّن، ومرشّحوه للمدير."""
    requests = (
        ErasureRequest.objects.filter(school=school)
        .select_related(
            "school", "student", "requested_by", "admin_signed_by", "dpo_signed_by", "reviewed_by"
        )
        .order_by("-created_at")
    )
    appoints = can_appoint(user, school)
    candidates: dict[str, str] = {}
    if appoints:
        for membership in (
            officer_candidates(school).select_related("user").order_by("user__full_name")
        ):
            candidates[str(membership.user_id)] = membership.user.full_name
    return {
        "rows": [_row(user, obj) for obj in requests],
        "officer": school.data_protection_officer,
        "can_appoint": appoints,
        "candidates": list(candidates.items()),
    }
