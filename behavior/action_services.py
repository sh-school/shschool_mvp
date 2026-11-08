"""اعتمادُ الإجراء المقترح ومتابعتُه وتجهيزُ المشرف — W-20261108-023 (قرارات المالك 2026-11-08).

- منسّقُ شؤون الطلبة يعتمد الإجراءَ ويتابع تنفيذَه (تمّ / لم يتمّ / جزئيّاً)؛ فإن كان هو من سجّل المخالفة
  اعتمدها النائبُ الإداريّ (vice_admin): من سجّل لا يعتمد.
- مشرفُ الجناح يجهّز التعهّدَ الخطّيّ والإحالةَ لطلبة جناحه وحدَهم (wings/scope.py) — لا يعتمد ولا يستدعي.
- الاختصاصيّان لا يعتمدان؛ تصلهما الإحالاتُ المعتمدة عند عتبات السياسة في قائمةٍ خاصّة.
- لا إشعارَ آليّاً لوليّ الأمر هنا: الاستدعاءُ والإشعارُ يدويّان بقدرة `behavior.summon_parent`.
- مسارُ لجنة الضبط (`behavior/services.py` و`committee_services.py`) لا يُمسّ.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from core.audit_repr import masked_repr
from core.models import AuditLog
from wings.scope import student_scope

from .models import BehaviorInfraction

COORDINATOR = "student_affairs_coordinator"
VICE_ADMIN = "vice_admin"
#: ما يجهّزه المشرفُ لكلّ نوعِ إجراءٍ مقترح: التعهّدُ الخطّيّ والإحالة فقط.
PREPARABLE = {
    "written_pledge": "written_pledge",
    "parent_pledge": "written_pledge",
    "social_specialist_referral": "referral",
}


class ActionError(Exception):
    """رفضٌ بسبب حالة المخالفة لا الصلاحية — رسالتُه عربيّةٌ تُعرض كما هي."""


def approver_role_for(infraction: BehaviorInfraction) -> str:
    """دورُ من يعتمد هذه المخالفة: المنسّق، فإن كان المنسّقُ مسجِّلَها فالنائبُ الإداريّ (فصلُ المهامّ)."""
    reporter = infraction.reported_by
    if reporter is not None and reporter.get_role() == COORDINATOR:
        return VICE_ADMIN
    return COORDINATOR


def may_decide(user: Any, infraction: BehaviorInfraction) -> bool:
    """هل يعتمد `user` هذه المخالفةَ ويتابعها؟ بدورٍ محدَّد، وليس مسجِّلَها نفسَه."""
    return user.pk != infraction.reported_by_id and user.get_role() == approver_role_for(infraction)


def _audit(user: Any, infraction: BehaviorInfraction, event: str, **changes: Any) -> None:
    """أثرٌ في سجلّ التدقيق: من فعل ماذا ومتى، بلا اسمٍ شخصيّ (`masked_repr`)."""
    AuditLog.objects.create(
        school=infraction.school,
        user=user,
        action="update",
        model_name="BehaviorInfraction",
        object_id=str(infraction.pk),
        object_repr=masked_repr(infraction),
        changes={"event": event, **changes},
    )


@transaction.atomic
def approve(infraction: BehaviorInfraction, user: Any, action_type: str = "") -> BehaviorInfraction:
    """يعتمد الإجراءَ المقترح (أو بديلاً يختاره المعتمِد من القائمة) فيصير ظاهراً في سجلّ الطالب."""
    if not may_decide(user, infraction):
        raise PermissionDenied("لا تعتمد هذه المخالفة")
    if infraction.approval_status != "pending":
        raise ActionError("هذه المخالفة ليست بانتظار الاعتماد.")
    labels = dict(BehaviorInfraction.DISCIPLINARY_ACTION_CHOICES)
    chosen = action_type or infraction.proposed_action_type
    if chosen not in labels:
        raise ActionError("اختر إجراءً من القائمة.")
    infraction.disciplinary_action_type = chosen
    infraction.action_taken = labels[chosen]
    infraction.approval_status = "approved"
    infraction.approved_by = user
    infraction.approved_at = timezone.now()
    infraction.save(
        update_fields=[
            "disciplinary_action_type",
            "action_taken",
            "approval_status",
            "approved_by",
            "approved_at",
        ]
    )
    _audit(
        user,
        infraction,
        "action_approved",
        action=chosen,
        proposed=infraction.proposed_action_type,
        source=infraction.proposed_source,
    )
    return infraction


@transaction.atomic
def record_followup(infraction: BehaviorInfraction, user: Any, status: str) -> BehaviorInfraction:
    """متابعةُ تنفيذ الإجراء المعتمد: تمّ، لم يتمّ، جزئيّاً."""
    if not may_decide(user, infraction):
        raise PermissionDenied("لا تتابع هذه المخالفة")
    if infraction.approval_status != "approved":
        raise ActionError("تُتابَع المخالفةُ بعد اعتماد إجرائها.")
    if status not in {"done", "not_done", "partial"}:
        raise ActionError("اختر حالةَ المتابعة.")
    infraction.followup_status = status
    infraction.save(update_fields=["followup_status"])
    _audit(user, infraction, "action_followup", status=status)
    return infraction


@transaction.atomic
def prepare(infraction: BehaviorInfraction, user: Any, kind: str) -> BehaviorInfraction:
    """يجهّز مشرفُ الجناح تعهّداً خطّيّاً أو إحالةً لطالبٍ من جناحه — لا اعتمادَ ولا استدعاء."""
    if user.get_role() != "admin_supervisor":
        raise PermissionDenied("التجهيز لمشرف الجناح")
    if not student_scope(user, infraction.school).covers_student(infraction.student_id):
        raise PermissionDenied("ليس من طلبة جناحك")
    if infraction.approval_status != "pending":
        raise ActionError("هذه المخالفة ليست بانتظار الاعتماد.")
    if kind not in PREPARABLE.values() or PREPARABLE.get(infraction.proposed_action_type) != kind:
        raise ActionError("هذا التجهيز لا يوافق الإجراءَ المقترح.")
    infraction.prepared_kind = kind
    infraction.prepared_by = user
    infraction.prepared_at = timezone.now()
    infraction.save(update_fields=["prepared_kind", "prepared_by", "prepared_at"])
    _audit(user, infraction, "action_prepared", kind=kind)
    return infraction
