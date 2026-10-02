"""نصابُ لجنة الضبط السلوكي — قرارٌ جماعيٌّ لا فرديّ (قرار المالك D-116م، W-20261001-024).

كان أيُّ عضوٍ واحدٍ يُنفّذ التصعيدَ أو الإيقافَ فوراً (`apply_committee_decision`). الآن:

- **التصعيد `escalate` والإيقاف `suspend`**: أغلبيّةُ الأعضاء المؤهَّلين على القرار نفسِه.
- **إغلاق المخالفة `resolve`**: عضوٌ واحدٌ مؤهَّلٌ كما كان — لا يمسّ حقَّ أحدٍ.
- **لا تفويض**: يصوّت العضوُ بنفسه، والغائبُ لا يُحتسب، والأغلبيّةُ تبقى من المؤهَّلين.
- **المؤهَّلون** = عضويّاتُ المدرسة النشطة بأدوار `COMMITTEE_ROLES` (المدير والنائبان والأخصائيّ
  الاجتماعيّ وspecialist). `is_superuser` لا يُحتسب صوتُه ما لم يكن عضواً — فلا يُكمل نصاباً وحدَه.
- مدرسةٌ بلا أعضاءٍ مؤهَّلين لا يُنفَّذ فيها شيء (فشلٌ مغلق).
"""

from __future__ import annotations

import logging

from django.db import transaction

from core.models import Membership

from .models import BehaviorCommitteeVote, BehaviorInfraction
from .services import BehaviorPermissions, BehaviorService

logger = logging.getLogger(__name__)

#: القراراتُ الجماعيّة وحدَها؛ `resolve` وما عداه يمرّ على المسار الفرديّ كما كان.
COLLECTIVE_DECISIONS = frozenset({"escalate", "suspend"})


def eligible_member_ids(school) -> set:
    """أعضاءُ اللجنة المؤهَّلون في المدرسة (مفاتيحُ المستخدمين)."""
    return set(
        Membership.objects.filter(
            school=school,
            is_active=True,
            role__name__in=BehaviorPermissions.COMMITTEE_ROLES,
        ).values_list("user_id", flat=True)
    )


def majority_needed(member_count: int) -> int:
    """أكثرُ من نصف الأعضاء المؤهَّلين."""
    return member_count // 2 + 1


def cast_vote(
    infraction: BehaviorInfraction,
    voter,
    decision: str,
    *,
    action: str = "",
    suspension_type: str = "internal",
    suspension_days: int = 1,
) -> tuple[str, str]:
    """يسجّل صوتَ العضو، وينفّذ القرارَ إن اكتملت الأغلبيّةُ عليه. يُعيد `(رسالة، مستوى)`."""
    if decision not in COLLECTIVE_DECISIONS:
        raise ValueError(f"قرارٌ غيرُ جماعيّ: {decision!r}")

    with transaction.atomic():
        # قفلُ المخالفة يمنع تنفيذَ القرار مرّتين حين يصوّت عضوان معاً.
        locked = BehaviorInfraction.objects.select_for_update().get(pk=infraction.pk)
        members = eligible_member_ids(locked.school)
        if voter.pk not in members:
            return "غير مسموح: لستَ من أعضاء اللجنة المؤهَّلين لهذا القرار الجماعي.", "error"

        if locked.is_resolved:
            return "المخالفةُ مغلقةٌ — لا تصويتَ عليها.", "error"

        BehaviorCommitteeVote.objects.update_or_create(
            infraction=locked,
            voter=voter,
            status=BehaviorCommitteeVote.OPEN,
            defaults={
                "decision": decision,
                "action_taken": action,
                "suspension_type": suspension_type,
                "suspension_days": suspension_days,
            },
        )

        needed = majority_needed(len(members))
        backing = list(
            BehaviorCommitteeVote.objects.filter(
                infraction=locked,
                status=BehaviorCommitteeVote.OPEN,
                decision=decision,
                voter_id__in=members,
            ).order_by("updated_at")
        )
        if len(backing) < needed:
            logger.info(
                "committee vote recorded infraction=%s decision=%s %s/%s",
                locked.pk,
                decision,
                len(backing),
                needed,
            )
            return (
                f"سُجّل صوتُك — {len(backing)} من {needed} لازمةٍ لتنفيذ القرار "
                f"(أغلبيّةُ {len(members)} أعضاء).",
                "info",
            )

        # معاملاتُ القرار: الأخفُّ مما اتّفقت عليه الأغلبيّة (أقلّ أيّام، والداخليُّ على الخارجيّ)،
        # ونصُّ الإجراء من العضو الذي أكمل النصاب الآن — لا من «آخر صفٍّ أُنشئ».
        message, level = BehaviorService.apply_committee_decision(
            infraction=locked,
            decision=decision,
            action=action,
            approved_by=voter,
            suspension_type=(
                "external" if all(v.suspension_type == "external" for v in backing) else "internal"
            ),
            suspension_days=min(v.suspension_days for v in backing),
        )
        open_votes = BehaviorCommitteeVote.objects.filter(
            infraction=locked, status=BehaviorCommitteeVote.OPEN
        )
        open_votes.filter(pk__in=[v.pk for v in backing]).update(
            status=BehaviorCommitteeVote.APPLIED
        )
        open_votes.update(status=BehaviorCommitteeVote.DROPPED)
        logger.info(
            "committee decision applied infraction=%s decision=%s votes=%s",
            locked.pk,
            decision,
            len(backing),
        )
        return message, level
