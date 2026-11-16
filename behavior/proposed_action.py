"""اقتراحُ إجراء المخالفة واعتمادُه (W-20261112-003، قراراتُ المالك 2026-11-08).

تُسجَّل المخالفةُ بلا إجراء؛ ويحسب النظامُ **اقتراحاً** من سلّم الدليل التنظيميّ بحسب الدرجة وتكرارِ
المخالفة. والاقتراحُ لا يُنفَّذ ولا يظهر لأسرةٍ ولا يُشعَر به وليُّ أمر: المنسّقُ يعتمده أو يختار غيره.

## مصدرُ الحقيقة

الجدولُ أدناه منقولٌ من `AAdocs/ministry_data/2026_2027/08_conduct_policy_2026.md` — المادة 3.5.3:
سلّمُ الدرجة الأولى المشترك (ص85–86، أسطرُ الملفّ 316–321) ومثالُ الدرجة الثانية المنصوصُ كاملاً
«عدم العناية بالمظهر» (ص87–88، الأسطر 350–355). و`marker` كلمةٌ من السطر نفسِه يتحقّق منها
الاختبارُ فلا ينجرف الرقمُ عن الملفّ. ما لم يُستخرج نصُّه (بقيّةُ الدرجة الثانية، والثالثة، والرابعة)
لا يُقترح آليّاً ولا يُخمَّن. والتكرارُ السادسُ وما بعده فصلٌ وتصعيدٌ لفريق السلوك: يبقيان في قرار
اللجنة الحاليّ (`behavior/services.py`) بلا تغيير.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from behavior.models import BehaviorInfraction

if TYPE_CHECKING:
    from core.models import CustomUser

SOURCE_MD = "AAdocs/ministry_data/2026_2027/08_conduct_policy_2026.md"
ARTICLE = "3.5.3"

#: من يعتمد الإجراء. والمنسّقُ الذي سجّل المخالفةَ لا يعتمدها: يعتمدها النائبُ الإداريّ (فصلُ المهامّ).
COORDINATOR = "student_affairs_coordinator"
DEPUTY = "vice_admin"
APPROVER_ROLES = frozenset({COORDINATOR, DEPUTY})
#: الاختصاصيّان يدرسان الحالةَ ولا يعتمدان.
SPECIALIST_ROLES = frozenset({"social_worker", "psychologist"})
#: ما لا يُعتمد من هنا: المحضرُ يحتاج وصفاً يُكتب عند التسجيل.
APPROVABLE_ACTIONS = tuple(
    (key, label)
    for key, label in BehaviorInfraction.DISCIPLINARY_ACTION_CHOICES
    if key != "incident_report"
)

#: التكرار ← (الإجراءُ المقترح، هل تصل الحالةُ للاختصاصيَّين، سطرُ الملفّ، كلمةٌ من السطر).
Rung = tuple[str, bool, int, str]
_NONE: Rung = ("", False, 0, "")
_D1: dict[int, Rung] = {
    1: ("verbal_warning", False, 316, "التنبيه الشفهي"),
    2: ("verbal_warning", False, 317, "التنبيه الشفهي"),
    3: ("social_specialist_referral", True, 318, "الاختصاصية الاجتماعية/النفسية"),
    4: ("written_pledge", False, 319, "تعهد الطالب خطياً"),
    5: ("social_specialist_referral", True, 320, "الاختصاصية الاجتماعية/النفسية"),
    6: ("", False, 321, "فصل مؤقت"),
}
_D2_APPEARANCE: dict[int, Rung] = {
    1: ("verbal_warning", False, 350, "تنبيه شفهي"),
    2: ("verbal_warning", False, 351, "تنبيه شفهي"),
    3: ("written_pledge", False, 352, "تعهد خطي"),
    4: ("written_pledge", False, 353, "تعهد خطي"),
    5: ("social_specialist_referral", True, 354, "الاختصاصي الاجتماعي/النفسي"),
    6: ("", False, 355, "فصل مؤقت"),
}
#: الجدولُ المنقول لكلّ (الدرجة، رمز المخالفة؛ فارغٌ = كلُّ مخالفات الدرجة).
LADDER_TABLE: dict[tuple[int, str], dict[int, Rung]] = {(1, ""): _D1, (2, "2-01"): _D2_APPEARANCE}

NOT_EXTRACTED = "لم يُستخرج نصُّ جدول هذه المخالفة من الدليل فلا يُقترح لها إجراءٌ آليّاً."
TO_TEAM = "من هذا التكرار يُرفع الأمر إلى فريق إدارة سلوك الطلبة ولجنة الضبط — لا اقتراحَ آليّ."
MANUAL_NOTE = "استدعاءُ وليّ الأمر وإشعارُه يدويّان من المنسّق."


@dataclass(frozen=True)
class Proposal:
    """ما يقترحه السلّم لمخالفةٍ مسجَّلة. `action` فارغٌ = لا اقتراحَ آليّ و`reason` يقول لماذا."""

    action: str = ""
    label: str = ""
    specialist: bool = False
    reason: str = ""
    article: str = ARTICLE
    md_line: int = 0

    @property
    def source(self) -> str:
        """رقمُ المادة وسطرُ الملفّ — يُعرضان بجوار الاقتراح."""
        return f"م{self.article} — {SOURCE_MD} سطر {self.md_line}" if self.md_line else ""


def suggest(degree: int, code: str, step: int) -> Proposal:
    """اقتراحُ السلّم لمخالفةٍ من درجة `degree` ورمز `code` في خطوة تكرارها `step`."""
    table = LADDER_TABLE.get((degree, code)) or LADDER_TABLE.get((degree, ""))
    if table is None:
        return Proposal(reason=NOT_EXTRACTED)
    action, specialist, md_line, _ = table.get(step, _NONE)
    if not action:
        return Proposal(reason=TO_TEAM, md_line=md_line)
    labels = dict(BehaviorInfraction.DISCIPLINARY_ACTION_CHOICES)
    return Proposal(action, labels[action], specialist, md_line=md_line)


def proposal_for(infraction: BehaviorInfraction) -> Proposal:
    """اقتراحُ مخالفةٍ مسجَّلة من درجتها ورمزها وخطوة تكرارها المخزَّنة عند التسجيل."""
    category = infraction.violation_category
    return suggest(infraction.level, category.code if category else "", infraction.escalation_step)


def is_pending(infraction: BehaviorInfraction) -> bool:
    """بانتظار الاعتماد: لم يُعتمد إجراؤها، وليست من الدرجة 3/4 (لجنةُ الضبط) ولا من الرصد الآليّ."""
    return (
        infraction.action_approved_at is None
        and infraction.level <= 2
        and not infraction.auto_rule
        and not infraction.disciplinary_action_type
    )


def can_approve(user: CustomUser, infraction: BehaviorInfraction) -> bool:
    """المنسّقُ يعتمد ما لم يسجّله بنفسه؛ والنائبُ الإداريّ يعتمد ما سجّله منسّق (من سجّل لا يعتمد)."""
    role = user.get_role()
    if role not in APPROVER_ROLES or infraction.reported_by_id == user.pk:
        return False
    if role == COORDINATOR:
        return True
    reporter = infraction.reported_by
    return reporter is not None and reporter.get_role() == COORDINATOR
