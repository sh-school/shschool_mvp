"""كتابةُ تجهيز الإجراء واعتمادِه ومتابعتِه (W-20261112-003) — كلُّ كتابةٍ بسجلّ تدقيق.

لا إشعارَ آليَّ لوليّ الأمر هنا: الاستدعاءُ والإشعارُ يدويّان من المنسّق بقدرة `behavior.summon_parent`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from behavior import proposed_action as pa
from behavior.models import BehaviorInfraction

if TYPE_CHECKING:
    from django.http import HttpRequest

    from core.models import CustomUser

_PREPARED = dict(BehaviorInfraction.PREPARED_KINDS)
_FOLLOWUPS = dict(BehaviorInfraction.FOLLOWUP_CHOICES)


def _audit(
    infraction: BehaviorInfraction,
    user: CustomUser,
    what: str,
    changes: dict[str, Any],
    request: HttpRequest | None,
) -> None:
    from core.models import AuditLog

    AuditLog.log(
        user=user,
        action="update",
        model_name="BehaviorInfraction",
        object_id=infraction.pk,
        object_repr=f"مخالفة سلوكية — {what}",
        changes=changes,
        school=infraction.school,
        request=request,
    )


@transaction.atomic
def prepare_action(
    *,
    infraction: BehaviorInfraction,
    user: CustomUser,
    kind: str,
    request: HttpRequest | None = None,
) -> None:
    """مشرفُ الجناح يجهّز تعهّداً خطّيّاً أو إحالةً — لا استدعاءَ ولا إدارةَ مخالفات. والنطاقُ يفحصه العرض."""
    if kind not in _PREPARED:
        raise ValueError("نوعُ التجهيز غير معروف.")
    if infraction.action_approved_at is not None:
        raise ValueError("اعتُمد إجراءُ هذه المخالفة فلا يُجهَّز بعده.")
    infraction.prepared_kind = kind
    infraction.prepared_by = user
    infraction.prepared_at = timezone.now()
    infraction.save(update_fields=["prepared_kind", "prepared_by", "prepared_at"])
    _audit(infraction, user, "تجهيز", {"prepared_kind": {"before": "", "after": kind}}, request)


@transaction.atomic
def approve_action(
    *,
    infraction: BehaviorInfraction,
    user: CustomUser,
    action: str,
    request: HttpRequest | None = None,
) -> None:
    """يعتمد الإجراءَ المختار — فيصير هو الإجراءَ المتّخذ للمخالفة. من سجّل المخالفةَ لا يعتمدها."""
    if not pa.can_approve(user, infraction):
        raise PermissionDenied("لا يحقّ لك اعتماد إجراء هذه المخالفة.")
    labels = dict(pa.APPROVABLE_ACTIONS)
    if action not in labels:
        raise ValueError("اختر إجراءً من القائمة.")
    if infraction.action_approved_at is not None:
        raise ValueError("اعتُمد إجراءُ هذه المخالفة من قبل.")
    suggested = pa.proposal_for(infraction).action
    infraction.disciplinary_action_type = action
    infraction.action_taken = labels[action]
    infraction.action_approved_by = user
    infraction.action_approved_at = timezone.now()
    infraction.save(
        update_fields=[
            "disciplinary_action_type",
            "action_taken",
            "action_approved_by",
            "action_approved_at",
        ]
    )
    _audit(
        infraction,
        user,
        "اعتماد الإجراء",
        {"approved_action": {"before": "", "after": action}, "suggested": suggested},
        request,
    )


@transaction.atomic
def record_followup(
    *,
    infraction: BehaviorInfraction,
    user: CustomUser,
    result: str,
    request: HttpRequest | None = None,
) -> None:
    """متابعةُ التنفيذ (تمّ، لم يتمّ، جزئيًّا) لإجراءٍ معتمد — بيدِ من يحقّ له الاعتماد."""
    if user.get_role() not in pa.APPROVER_ROLES:
        raise PermissionDenied("لا يحقّ لك متابعة تنفيذ الإجراء.")
    if result not in _FOLLOWUPS:
        raise ValueError("نتيجةُ المتابعة غير معروفة.")
    if infraction.action_approved_at is None:
        raise ValueError("لا متابعةَ قبل اعتماد الإجراء.")
    before = infraction.action_followup
    infraction.action_followup = result
    infraction.save(update_fields=["action_followup"])
    _audit(
        infraction,
        user,
        "متابعة التنفيذ",
        {"action_followup": {"before": before, "after": result}},
        request,
    )
