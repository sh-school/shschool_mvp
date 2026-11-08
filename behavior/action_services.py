"""تجهيزُ إجراء المخالفة واعتمادُه (W-20261108-007، طلب CA7E وقرارات المالك 2026-11-08).

الدورة: يُسجَّل الرصدُ بلا إجراء ← يقترح النظامُ إجراءَ السلّم المعتمد (`action_proposal.py`) ← يجهّز مشرفُ
الجناح التعهّدَ الخطّيّ أو الإحالةَ لطلبة جناحه ← يتابع المنسّقُ (تمّ/لم يتمّ/جزئيّاً) ويعتمد ←
تصل الإحالاتُ عند العتبات للاختصاصيّين لدراسة الحالة.

فصلُ المهامّ: من سجّل المخالفةَ لا يعتمدها. فإن سجّلها المنسّقُ نفسُه اعتمدها النائبُ الإداريّ.
ولا إشعارَ آليّاً لوليّ الأمر هنا: الاستدعاءُ يدويٌّ بقدرة `behavior.summon_parent`. ولجنةُ الضبط
والإيقافُ في `services.py` لا يمسّها شيء.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from behavior.action_proposal import propose
from behavior.models import BehaviorInfraction

COORDINATOR = "student_affairs_coordinator"
DEPUTY = "vice_admin"
FOLLOW_UPS = ("done", "not_done", "partial")
PREPARE_KINDS = ("written_pledge", "referral")


def attach_proposal(infraction: BehaviorInfraction) -> bool:
    """يكتب اقتراحَ السلّم على المخالفة إن وُجد نصُّه.

    التكرارُ هو `escalation_step` الذي حسبه `create_infraction` من التاريخ (بلا قصٍّ دون آخر السلّم
    للتكرارات الخمسة المستخرجة)؛ والرصدُ الآليُّ (`auto_rule`) لا يُقترح له شيء.
    """
    category = infraction.violation_category
    if category is None or infraction.auto_rule:
        return False
    found = propose(category.code, infraction.escalation_step)
    if found is None:
        return False
    infraction.proposed_rep = found.repetition
    infraction.proposed_text = found.text
    infraction.proposed_source = found.source
    infraction.proposed_specialist = found.specialist
    infraction.approval_status = "pending"
    infraction.save(
        update_fields=[
            "proposed_rep",
            "proposed_text",
            "proposed_source",
            "proposed_specialist",
            "approval_status",
        ]
    )
    return True


def approver_may_approve(user: Any, infraction: BehaviorInfraction) -> bool:
    """المنسّقُ يعتمد ما لم يسجّله؛ والنائبُ الإداريّ يعتمد ما سجّله المنسّق. ومن سجّل لا يعتمد أبداً."""
    if user.pk == infraction.reported_by_id:
        return False
    role = user.get_role()
    if role == COORDINATOR:
        return True
    reporter = infraction.reported_by
    return role == DEPUTY and reporter is not None and reporter.get_role() == COORDINATOR


def _audit(
    user: Any, infraction: BehaviorInfraction, what: str, request: Any, **changes: Any
) -> None:
    from core.models import AuditLog

    AuditLog.log(
        user=user,
        action="update",
        model_name="BehaviorInfraction",
        object_id=infraction.pk,
        object_repr=f"إجراء المخالفة — {what}",
        changes=changes or None,
        school=infraction.school,
        request=request,
    )


@transaction.atomic
def prepare_action(
    infraction: BehaviorInfraction, user: Any, kind: str, request: Any = None
) -> BehaviorInfraction:
    """مشرفُ الجناح يجهّز تعهّداً خطّيّاً أو إحالةً — لا استدعاءَ ولا إدارة. والنطاقُ يفحصه المستدعي."""
    if kind not in PREPARE_KINDS:
        raise ValueError("نوعُ التجهيز غير معروف")
    if infraction.approval_status != "pending":
        raise PermissionDenied("لا إجراءَ بانتظار الاعتماد على هذه المخالفة")
    infraction.prepared_kind = kind
    infraction.prepared_by = user
    infraction.prepared_at = timezone.now()
    infraction.save(update_fields=["prepared_kind", "prepared_by", "prepared_at"])
    _audit(user, infraction, "تجهيز", request, prepared=kind)
    return infraction


@transaction.atomic
def approve_action(
    infraction: BehaviorInfraction, user: Any, follow_up: str, request: Any = None
) -> BehaviorInfraction:
    """يسجّل متابعةَ المنسّق ويعتمد الإجراء، ويدقّق ذلك. يرفض من سجّل أو من لا يملك الاعتماد."""
    if follow_up not in FOLLOW_UPS:
        raise ValueError("المتابعةُ: تمّ أو لم يتمّ أو جزئيّاً")
    if infraction.approval_status != "pending" or not approver_may_approve(user, infraction):
        raise PermissionDenied("لا يحقّ لك اعتمادُ هذا الإجراء")
    infraction.approval_status = "approved"
    infraction.follow_up = follow_up
    infraction.approved_by = user
    infraction.approved_at = timezone.now()
    infraction.save(update_fields=["approval_status", "follow_up", "approved_by", "approved_at"])
    _audit(
        user, infraction, "اعتماد", request, follow_up=follow_up, source=infraction.proposed_source
    )
    return infraction
