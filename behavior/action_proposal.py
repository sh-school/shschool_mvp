"""اقتراحُ الإجراء من سلّم المخالفات — W-20261108-023 (قرارات المالك 2026-11-08).

المصدر: AAdocs/ministry_data/2026_2027/08_conduct_policy_2026.md، المادة 3.5.3 (طلبة الصفّ الرابع حتى
الثاني عشر): جدولُ الدرجة الأولى المشترك (ص85–86، الأسطر 316–321) ومثالُ «عدم العناية بالمظهر» من الدرجة
الثانية (ص87–88، الأسطر 350–355). والعتباتُ والإجراءاتُ هنا منقولةٌ من نصّهما لا من الذاكرة.

ما لم يُستخرج نصُّه في الملفّ — بقيّةُ جداول الدرجة الثانية والدرجتان الثالثة والرابعة — **لا يُقترح له
شيءٌ آليّاً** ولا يُخمَّن، فيبقى لقرار المنسّق أو اللجنة كما كان. والتكرارُ السادسُ وما بعده (فريق إدارة
سلوك الطلبة والفصلُ المؤقّت والإحالةُ إلى قسم الحماية) من مسار لجنة الضبط القائم فلا اقتراحَ له أيضاً.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_FILE = "AAdocs/ministry_data/2026_2027/08_conduct_policy_2026.md"


@dataclass(frozen=True)
class Proposal:
    """اقتراحٌ لتكرارٍ بعينه: نوعُ الإجراء (من قائمة النموذج)، وهل هو عتبةُ إحالةٍ للاختصاصيّين، وسندُه."""

    action_type: str
    specialist: bool
    source: str
    repetition: int


@dataclass(frozen=True)
class _Row:
    action_type: str
    line: int
    specialist: bool = False


#: الدرجةُ الأولى — سلّمٌ واحدٌ للمخالفات التسع (م3.5.3، ص85–86). التكرارُ السادس: فريقُ السلوك (لجنة).
_D1_SOURCE = f"{_FILE} م3.5.3 ص85–86"
_D1 = (
    _Row("verbal_warning", 316),  # الأولى: تنبيهٌ شفهيّ انفراديّ — المعلّم
    _Row("verbal_warning", 317),  # الثانية: تنبيهٌ شفهيّ + إشعارُ وليّ الأمر (يدويّ) — المشرف
    _Row("social_specialist_referral", 318, specialist=True),  # الثالثة: الاختصاصيّان — دراسةُ الحالة
    _Row("written_pledge", 319),  # الرابعة: تعهّدُ الطالب خطّيّاً (1) + إحالةٌ للمشرفة
    _Row("social_specialist_referral", 320, specialist=True),  # الخامسة: الاختصاصيّان — خطّةُ التدخّل
)

#: الدرجةُ الثانية — «عدم العناية بالمظهر الشخصيّ» وحدَها (م3.5.3، ص87–88).
_D2_APPEARANCE_SOURCE = f"{_FILE} م3.5.3 ص87–88"
_D2_APPEARANCE = (
    _Row("verbal_warning", 350),
    _Row("verbal_warning", 351),
    _Row("written_pledge", 352),  # الثالثة: تعهّدٌ خطّيّ (1) + إحالةٌ لمنسّق شؤون الطلبة
    _Row("parent_summons", 353),  # الرابعة: طلبُ استدعاء وليّ الأمر + تعهّدٌ خطّيّ (2) — الاستدعاءُ يدويّ
    _Row("social_specialist_referral", 354, specialist=True),  # الخامسة: الاختصاصيّان
)

#: مفتاحُ السلّم في `conduct_2026.BY_CODE` ← (الصفوف، سند الجدول). المفتاحُ هويّةُ السلّم فحسب لا عتبةٌ منه.
_RULES = {
    "d1": (_D1, _D1_SOURCE),
    "d2_appearance": (_D2_APPEARANCE, _D2_APPEARANCE_SOURCE),
}


def propose(violation_code: str, repetition: int) -> Proposal | None:
    """اقتراحُ الإجراء للمخالفة `violation_code` في تكرارها رقم `repetition` (يبدأ من 1) — أو ``None``.

    ``None`` لمخالفةٍ لم يُستخرج جدولُها من الملفّ، ولتكرارٍ فاتت الصفوفَ المنقولة (مسارُ اللجنة).
    """
    from .conduct_2026 import BY_CODE

    item = BY_CODE.get(violation_code)
    rule = _RULES.get(item.ladder) if item is not None else None
    if rule is None or repetition < 1:
        return None
    rows, source = rule
    if repetition > len(rows):
        return None
    row = rows[repetition - 1]
    return Proposal(row.action_type, row.specialist, f"{source} سطر {row.line}", repetition)


def ladder(
    student: Any, school: Any, level: int, violation_category: Any, session: Any, chosen_action: str
) -> dict[str, Any]:
    """حقولُ اقتراح الإجراء للمخالفة الجديدة — فارغةٌ إن اختار المسجِّلُ إجراءً أو لا سلّمَ منقولاً لها.

    الاقتراحُ لا يُكتب في `action_taken` ولا `disciplinary_action_type` (فهما ما يراه أهلُ الطالب)،
    بل في حقوله هو، وحالتُه «بانتظار الاعتماد» حتى يعتمده منسّقُ شؤون الطلبة.
    """
    from .services import BehaviorService

    if chosen_action or violation_category is None:
        return {}
    prior = BehaviorService.get_prior_infraction_count(
        student, school, level, violation_category, session=session
    )
    found = propose(violation_category.code, prior + 1)
    if found is None:
        return {}
    return {
        "proposed_action_type": found.action_type,
        "proposed_source": found.source,
        "proposed_repetition": found.repetition,
        "proposed_specialist": found.specialist,
        "approval_status": "pending",
    }
