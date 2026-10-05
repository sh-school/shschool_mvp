"""نصابُ لجنة الضبط السلوكي — قرارٌ جماعيٌّ لا فرديّ (قرار المالك D-116م، W-20261001-024).

كان أيُّ عضوٍ واحدٍ يُنفّذ التصعيدَ أو الإيقافَ فوراً (`apply_committee_decision`). الآن:

- **التصعيد `escalate` والإيقاف `suspend`**: أغلبيّةُ الأعضاء المؤهَّلين على القرار نفسِه.
- **إغلاق المخالفة `resolve`**: عضوٌ واحدٌ مؤهَّلٌ كما كان — لا يمسّ حقَّ أحدٍ.
- **المُبلِّغ عن المخالفة لا يصوّت عليها** (تضاربُ مصلحة)، ويُحسب النصابُ من بقيّة المؤهَّلين.
- **لا تفويض**: يصوّت العضوُ بنفسه، والغائبُ لا يُحتسب، والأغلبيّةُ تبقى من المؤهَّلين.
- **المؤهَّلون** = عضويّاتُ المدرسة النشطة بأدوار `COMMITTEE_ROLES` (المدير والنائبان والأخصائيّ
  الاجتماعيّ وspecialist). `is_superuser` لا يُحتسب صوتُه ما لم يكن عضواً — فلا يُكمل نصاباً وحدَه.
- مدرسةٌ بلا أعضاءٍ مؤهَّلين لا يُنفَّذ فيها شيء (فشلٌ مغلق).
"""

from __future__ import annotations

import logging

from django.db import transaction

from core.models import Membership, StudentEnrollment
from core.permissions import BEHAVIOR_COMMITTEE_CASE_SCOPED
from core.unrestricted_role import has_unrestricted_role

from .models import BehaviorCommitteeVote, BehaviorInfraction
from .services import BehaviorPermissions, BehaviorService

logger = logging.getLogger(__name__)

#: القراراتُ الجماعيّة وحدَها؛ `resolve` وما عداه يمرّ على المسار الفرديّ كما كان.
COLLECTIVE_DECISIONS = frozenset({"escalate", "suspend"})


#: أدوارُ اللجنة التي تصوّت في كلّ قضيّة — وما عداها (المشرفُ الإداريّ) يصوّت في قضيّة جناحه وحدَها.
SCHOOL_WIDE_ROLES = frozenset(BehaviorPermissions.COMMITTEE_ROLES) - BEHAVIOR_COMMITTEE_CASE_SCOPED


def case_supervisor_id(infraction: BehaviorInfraction):
    """مشرفُ جناح الطالب الإداريّ اليومَ — أصيلاً أو بديلاً مغطّياً — إن كان بدور «مشرف إداريّ»، وإلّا `None`.

    «واحدٌ لكلّ قضيّة»: من يحمل الجناحَ بسؤال `Wing.current_supervisor` نفسِه الذي تمرّ عليه كلُّ
    صلاحيّةٍ في الجناح. وبديلٌ من غير هذا الدور (ملاحظُ طلبةٍ مثلاً) ليس عضواً بالمادّة 5.7.
    """
    enrollment = StudentEnrollment.objects.current_of(infraction.student, infraction.school)
    wing = enrollment.class_group.wing if enrollment else None
    holder = wing.current_supervisor() if wing is not None and wing.is_active else None
    if holder is None:
        return None
    is_supervisor = Membership.objects.filter(
        school=infraction.school, user=holder, is_active=True, role__name="admin_supervisor"
    ).exists()
    return holder.pk if is_supervisor else None


def may_act_on(user, infraction: BehaviorInfraction) -> bool:
    """أيعمل هذا العضوُ في هذه القضيّة؟ — أعضاءُ المدرسة كلُّهم، والمشرفُ لجناح طالبها وحدَه."""
    if user.is_superuser or has_unrestricted_role(user):
        return True
    role = user.get_role()
    if role in BEHAVIOR_COMMITTEE_CASE_SCOPED:
        return user.pk == case_supervisor_id(infraction)
    return role in BehaviorPermissions.COMMITTEE_ROLES


def eligible_member_ids(school, infraction: BehaviorInfraction | None = None) -> set:
    """أعضاءُ اللجنة المؤهَّلون (مفاتيحُ المستخدمين).

    الأدوارُ العامّةُ لكلّ قضيّة، ومع `infraction` يُضاف مشرفُ جناح طالبها (واحدٌ لا كلُّ المشرفين) ويُستبعد
    المُبلِّغُ عنها (تضاربُ مصلحة — قرارُ المالك تكملةً لـD-116م)، فيُحسب النصابُ من بقيّة المؤهَّلين.
    """
    members = set(
        Membership.objects.filter(
            school=school,
            is_active=True,
            role__name__in=SCHOOL_WIDE_ROLES,
        ).values_list("user_id", flat=True)
    )
    if infraction is not None:
        supervisor_id = case_supervisor_id(infraction)
        if supervisor_id is not None:
            members.add(supervisor_id)
        members.discard(infraction.reported_by_id)
    return members


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
        members = eligible_member_ids(locked.school, locked)
        if voter.pk == locked.reported_by_id:
            return "غير مسموح: المُبلِّغُ عن المخالفة لا يصوّت عليها (تضاربُ مصلحة).", "error"
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


def decide_committee(infraction: BehaviorInfraction, user, post) -> tuple[str, str]:
    """قرارُ اللجنة من حقول النموذج: جماعيٌّ (صوت) أو فرديٌّ (تنفيذٌ فوريّ)، ويردّ (رسالة، مستوى).

    مكانُه الخدمة لا العرض: قراءةُ الحقول وضبطُ حدودها (أيّام الإيقاف 1..365) وتوزيعُ الجماعيّ
    على الفرديّ منطقُ أعمال، والعرضُ يستدعيه ويعرض نتيجته فقط.
    """
    decision = post.get("decision")
    action = post.get("action_taken", "").strip()
    suspension_type = "external" if post.get("suspension_type") == "external" else "internal"
    try:
        suspension_days = min(365, max(1, int(post.get("suspension_days") or 1)))
    except ValueError:
        suspension_days = 1
    if decision in COLLECTIVE_DECISIONS:
        # التصعيد والإيقاف قرارٌ جماعيّ بأغلبيّة الأعضاء (D-116م) — صوتٌ لا تنفيذٌ فوريّ.
        return cast_vote(
            infraction,
            user,
            decision,
            action=action,
            suspension_type=suspension_type,
            suspension_days=suspension_days,
        )
    # نظام النقاط ملغى — restore_pts=0 دائماً
    return BehaviorService.apply_committee_decision(
        infraction=infraction,
        decision=decision,
        action=action,
        restore_pts=0,
        reason="",
        approved_by=user,
        suspension_type=suspension_type,
        suspension_days=suspension_days,
    )
