"""اقتراحُ الإجراء من سلّم المخالفات المعتمد وتجهيزُه واعتمادُه (W-20261108-027، قرارُ المالك 2026-11-08).

المصدر: AAdocs/ministry_data/2026_2027/08_conduct_policy_2026.md م3.5.3 — جداولُ الإجراءات البعديّة
بحسب الدرجة والتكرار (ص85–125). والعتباتُ والإجراءاتُ تُقرأ من `conduct_2026.LADDERS` المنقولةِ
عن ذلك الجدول لا من الذاكرة.

ما يقترحه النظامُ آليّاً: الدرجتان الأولى والثانية فقط؛ فنصُّ الدرجتين الثالثة والرابعة لم يُستخرج
من المصدر استخراجاً يُعتمد عليه، فلا يُقترح لهما شيء (قرارُ المالك). والدرجةُ الرابعة والإيقافُ والتصعيد
تبقى في قرار لجنة الضبط (`BehaviorService`) بلا تغيير.

لا إشعارَ آليّاً لوليّ الأمر هنا: الاستدعاءُ والإشعارُ يدويّان من المنسّق بقدرة
`behavior.summon_parent`. وحقولُ الاقتراح للكادر وحدَه فلا يقرؤها عرضُ الطالب ولا وليّ الأمر.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.utils import timezone

from behavior.conduct_2026 import BY_CODE, PS, SW, SWPS

if TYPE_CHECKING:
    from django.http import HttpRequest

    from behavior.models import BehaviorInfraction
    from core.models import CustomUser

#: الدرجاتُ التي استُخرج نصُّ جداولها فيُقترح لها الإجراء.
PROPOSABLE_DEGREES = (1, 2)

SOURCE_FILE = "AAdocs/ministry_data/2026_2027/08_conduct_policy_2026.md"
ARTICLE = "م3.5.3"

_SPECIALIST_ACTORS = frozenset({SW, PS, SWPS})

#: ما يجهّزه مشرفُ الجناح: التعهّدُ الخطّيّ والإحالةُ فقط — لا استدعاءَ ولا إدارةَ مخالفات.
PREPARABLE = ("written_pledge", "referral")
FOLLOW_UPS = ("done", "not_done", "partial")

COORDINATOR_ROLE = "student_affairs_coordinator"
DEPUTY_ROLE = "vice_admin"

SAME_PERSON_REFUSAL = "من سجّل المخالفة لا يعتمد إجراءها."
DEPUTY_ONLY_REFUSAL = "المخالفةُ سجّلها منسّقُ شؤون الطلبة، فيعتمدها النائبُ الإداريّ."


@dataclass(frozen=True)
class Proposal:
    text: str
    basis: str
    specialist_line: str


def propose(category: Any, step: int) -> Proposal | None:
    """إجراءُ التكرار `step` من سلّم فئة المخالفة، أو None إن لم تكن للفئة درجةٌ مستخرجةٌ نصُّها."""
    item = BY_CODE.get(getattr(category, "code", ""))
    if item is None or item.degree not in PROPOSABLE_DEGREES:
        return None
    ladder = item.steps
    number = max(1, min(step, len(ladder.steps)))
    rows = ladder.step(number)
    where = f"{ARTICLE} ص{ladder.pages}"
    specialist = " · ".join(action for actor, action in rows if actor in _SPECIALIST_ACTORS)
    return Proposal(
        text=" · ".join(f"{actor}: {action}" for actor, action in rows),
        basis=f"{SOURCE_FILE} {where} — التكرار {number}",
        specialist_line=f"{where} التكرار {number}: {specialist}" if specialist else "",
    )


def proposal_fields(category: Any, step: int) -> dict[str, str]:
    """حقولُ الاقتراح التي تُكتب مع المخالفة — فارغةٌ إن لم يكن لها اقتراح."""
    proposal = propose(category, step)
    if proposal is None:
        return {}
    return {
        "proposed_action": proposal.text,
        "proposed_basis": proposal.basis,
        "specialist_line": proposal.specialist_line,
        "approval_status": "pending",
    }


def approval_refusal(infraction: BehaviorInfraction, user: CustomUser) -> str:
    """سببُ منع المستخدم من اعتماد هذه المخالفة، أو فارغٌ إن جاز له (فصلُ المهامّ: من سجّل لا يعتمد)."""
    reporter = infraction.reported_by
    if reporter is not None and reporter.pk == user.pk:
        return SAME_PERSON_REFUSAL
    if reporter is not None and reporter.get_role() == COORDINATOR_ROLE:
        if user.get_role() != DEPUTY_ROLE:
            return DEPUTY_ONLY_REFUSAL
    return ""


def _audit(
    request: HttpRequest | None, user: CustomUser, infraction: BehaviorInfraction, event: str
) -> None:
    """سجلُّ التدقيق معرّفٌ مقنَّع: لا نصَّ مخالفةٍ ولا اسمَ طالب."""
    from core.models import AuditLog

    AuditLog.log(
        user=user,
        action="update",
        model_name="BehaviorInfraction",
        object_id=infraction.pk,
        object_repr=f"مخالفة سلوكية — {event}",
        changes={"event": event, "follow_up": infraction.follow_up},
        school=infraction.school,
        request=request,
    )


def approve(
    infraction: BehaviorInfraction,
    user: CustomUser,
    follow_up: str,
    request: HttpRequest | None = None,
) -> None:
    """يعتمد المنسّقُ (أو النائبُ الإداريّ) الإجراءَ المقترح مع متابعته. ValueError برسالةٍ عربيّة إن لم يجز."""
    if infraction.approval_status != "pending":
        raise ValueError("لا اقتراحَ بانتظار الاعتماد لهذه المخالفة.")
    if follow_up not in FOLLOW_UPS:
        raise ValueError("اختر المتابعة: تمّ أو لم يتمّ أو جزئيًّا.")
    refusal = approval_refusal(infraction, user)
    if refusal:
        raise ValueError(refusal)
    infraction.approval_status = "approved"
    infraction.follow_up = follow_up
    infraction.approved_by = user
    infraction.approved_at = timezone.now()
    infraction.save(  # type: ignore[no-untyped-call]
        update_fields=["approval_status", "follow_up", "approved_by", "approved_at"]
    )
    _audit(request, user, infraction, "approve_action")


def prepare(
    infraction: BehaviorInfraction,
    user: CustomUser,
    kind: str,
    request: HttpRequest | None = None,
) -> None:
    """يجهّز مشرفُ الجناح تعهّداً خطّيّاً أو إحالةً قبل اعتماد المنسّق. ValueError إن لم يجز."""
    if kind not in PREPARABLE:
        raise ValueError("المسموح للمشرف: تجهيز تعهّدٍ خطّيّ أو إحالة.")
    if infraction.approval_status != "pending":
        raise ValueError("لا اقتراحَ بانتظار الاعتماد لهذه المخالفة.")
    infraction.prepared_action = kind
    infraction.prepared_by = user
    infraction.prepared_at = timezone.now()
    infraction.save(  # type: ignore[no-untyped-call]
        update_fields=["prepared_action", "prepared_by", "prepared_at"]
    )
    _audit(request, user, infraction, f"prepare_{kind}")
