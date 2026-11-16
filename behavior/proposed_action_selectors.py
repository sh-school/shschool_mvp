"""قراءةُ طوابير اعتماد الإجراء (W-20261112-003) — العرضُ يستدعي دالّةً واحدة ويأخذ ما يحتاجه دفعة."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from behavior import proposed_action as pa
from behavior.models import BehaviorInfraction

if TYPE_CHECKING:
    from core.models import CustomUser, School
    from wings.scope import StudentScope

#: سقفُ ما يُعرض في كلّ قائمة — الأحدثُ أولاً.
LIMIT = 200


@dataclass(frozen=True)
class Row:
    """صفٌّ في قائمة: المخالفةُ واقتراحُها وما يحقّ لصاحب الشاشة فعلُه بها."""

    infraction: BehaviorInfraction
    proposal: pa.Proposal
    can_approve: bool = False


@dataclass
class Queues:
    """قوائمُ الصفحة: بانتظار الاعتماد، وللمتابعة، وإحالاتُ الاختصاصيَّين."""

    pending: list[Row] = field(default_factory=list)
    followups: list[Row] = field(default_factory=list)
    referrals: list[Row] = field(default_factory=list)


def _base(school: School, scope: StudentScope) -> Any:
    qs = BehaviorInfraction.objects.filter(school=school, level__lte=2, auto_rule="")
    return scope.narrow(
        qs.select_related("student", "violation_category", "reported_by", "prepared_by"),
    ).order_by("-date", "-created_at")


def queues_for(user: CustomUser, school: School, scope: StudentScope) -> Queues:
    """قوائمُ هذا المستخدم بحسب دوره: الاختصاصيّان لا يرون إلّا إحالاتِهما، والمشرفُ جناحَه وحدَه."""
    role = user.get_role()
    result = Queues()
    if role in pa.SPECIALIST_ROLES:
        approved = _base(school, scope).filter(action_approved_at__isnull=False)[:LIMIT]
        for item in approved:
            proposal = pa.proposal_for(item)
            if proposal.specialist or item.disciplinary_action_type == "social_specialist_referral":
                result.referrals.append(Row(item, proposal))
        return result
    pending = _base(school, scope).filter(
        action_approved_at__isnull=True, disciplinary_action_type=""
    )
    result.pending = [
        Row(item, pa.proposal_for(item), pa.can_approve(user, item)) for item in pending[:LIMIT]
    ]
    if role in pa.APPROVER_ROLES:
        done = _base(school, scope).filter(action_approved_at__isnull=False, action_followup="")
        result.followups = [Row(item, pa.proposal_for(item), True) for item in done[:LIMIT]]
    return result
