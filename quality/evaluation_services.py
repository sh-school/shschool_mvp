"""
quality/evaluation_services.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
حفظُ تقييم أداء الموظّف — المسارُ الوحيد الذي يكتب الدرجاتِ والمستوى.

يستدعيه `quality.evaluation_views.create_evaluation`، وفيه تُفحص قيودُ المستوى قبل
أيّ كتابة، على التقرير السنويّ الوزاريّ (S2) وحده.

المرجع — النظام الوظيفي لموظفي المدارس (قرار مجلس الوزراء 32/2019)،
`data/2026-2027/02- شؤون الموظفين/02- النظام الوظيفي لموظفي المدارس.pdf`
(ممسوحٌ بلا طبقة نصّ؛ قُرئ من الصورة)، ونقلُه في `02_staff_affairs.md:208-210`:

  - المادة 17 (صفحة الملفّ 11، المطبوعة 25) — لا «ممتاز» لمن:
      (1) أُتيحت له فرصةُ تدريبٍ «ولم يجتزه بنجاح»؛
      (2) وقع عليه جزاءٌ تأديبيٌّ بالخصم أو الوقف «لمدة تزيد على خمسة أيام»، أو جزاءاتٌ
          «تجاوز مجموعها … لمدة تزيد على عشرة أيام» خلال العام، «أو أي جزاء آخر أشد»؛
      (3) انقطع بدون عذرٍ مقبول «مدة تزيد على خمسة أيام».
  - المادة 18 (صفحة الملفّ 12، المطبوعة 26) — لا «ممتاز» ولا «جيد جداً» لمن:
      (1) أُتيحت له فرصةُ التدريب «وتخلف عنه دون عذر مقبول»؛
      (2) جزاءٌ «لمدة تزيد على عشرة أيام»، أو جزاءاتٌ «يجاوز مجموعها … خمسة عشر يوماً»،
          «أو أي جزاء آخر أشد»؛
      (3) انقطاعٌ «مدة تزيد على عشرة أيام».
  - المادة 19 (الصفحة نفسها) — «ضعيف» لمن «لم يحصل على الرخصة المهنية خلال المدة
    التي تحددها الإدارة المختصة، أو لم يقم بتجديدها».

وحدُّ مجموع المادة 18 **خمسة عشر** يوماً: هكذا في القرار وفي مربّع المادة بالاستمارات
الخمس التي تحمله (الفئة العمالية، والإداريّة 1 و2 و3، والنائب الإداري — ص1). وكان
`06_attendance_performance_review.md:110` يقول «خمسة وعشرين» خطأَ نسخٍ صُحّح.
وكلُّ العتبات «تزيد على»/«يجاوز»: أكبر تماماً، فالعتبةُ نفسُها لا تمنع.
والقيودُ تسري على كلّ موظّفٍ بنصّ القرار، وإن لم تُطبع في استمارتَي المعلم والنائب
الأكاديمي.

وما لا يُحتسب هنا عمداً: الإنذار واللوم (لا تذكرهما المادتان)، والإيقافُ الاحتياطيّ
على ذمّة التحقيق (المادة 34 — إجراءٌ «مع استمرار صرف راتبه الإجمالي» لا جزاءٌ
تأديبيّ)، والتأخّرُ بذاته.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from core.models import Membership

from .evaluation_selectors import get_employee_role, get_school_roles
from .models import EmployeeEvaluation, EvaluationScore, RoleEvaluationTemplate
from .reporting_lines import may_place, rejection_reason

if TYPE_CHECKING:
    from core.models import CustomUser, School

#: (مفتاح المحور، اسمه، درجته القصوى) — كما يبنيها `get_axes_for_employee`.
AxisSpec = tuple[str, str, int]

DEFAULT_AXIS_FIELDS = frozenset(EmployeeEvaluation._AXIS_FIELDS)
_EVALUATOR_STATUSES = frozenset({"draft", "submitted"})

# ── عتباتُ المادتين 17 و18 (القرار 32/2019، صفحتا الملفّ 11 و12) — كلُّها «تزيد على» ──
ART17_SINGLE_SANCTION_DAYS = 5
ART17_SANCTION_DAYS_TOTAL = 10
ART17_UNEXCUSED_ABSENCE_DAYS = 5
ART18_SINGLE_SANCTION_DAYS = 10
ART18_SANCTION_DAYS_TOTAL = 15
ART18_UNEXCUSED_ABSENCE_DAYS = 10

_EXCELLENT = frozenset({"excellent"})
_EXCELLENT_OR_VERY_GOOD = frozenset({"excellent", "very_good"})
_ALL_BUT_WEAK = frozenset({"excellent", "very_good", "good", "acceptable"})


_ACADEMIC_YEAR = re.compile(r"^(\d{4})-(\d{4})$")
_LOCKED_STATUSES = frozenset({"approved", "acknowledged"})


class EvaluationRejectedError(ValueError):
    """تقييمٌ لا يُحفظ — الرسالةُ تُعرض للمقيِّم كما هي."""


#: «وتتولى لجنة شؤون المدارس، تقييم أداء مديري المدارس سنوياً» — المادة 15،
#: «02- النظام الوظيفي لموظفي المدارس.pdf» صفحة الملفّ 10 (02_staff_affairs.md:199). وصدرُ
#: المادة: «مع مراعاة أحكام نظام تقييم الأداء المنصوص عليها في القانون» — والقانونُ (الموارد
#: البشرية المدنية) ليس في مجلّد المصادر، فلا يُبنى عليه هنا حكم.
PRINCIPAL_NOT_EVALUATED = (
    "تقييمُ مدير المدرسة للجنة شؤون المدارس لا للمدرسة — المادة 15 (02_staff_affairs.md:199)"
)

#: «يضع الرئيس المباشر تقييم أداء الموظف ويعتمد من مدير المدرسة» — المادة 16، صفحة الملفّ 10
#: (02_staff_affairs.md:200). والموظّفُ ليس رئيسَ نفسه، فلا يضع تقريرَه ولا متابعتَه.
SELF_EVALUATION = (
    "لا يضع الموظّفُ تقييمَه عن نفسه — «يضع الرئيس المباشر تقييم أداء الموظف» (المادة 16)."
)


#: قالبُ التقرير السنويّ لم يعد استمارةَ دوره المطبوعة (وزنٌ أو محورٌ تغيّر بعد البذر). والمخرجُ
#: `seed_quality_templates --apply`: يعيده إلى الاستمارة ويُرجع ما عليه مسودّةً (`appraisal_seed`)،
#: ما لم يكن عليه تقريرٌ معتمَد.
TEMPLATE_OFF_FORM = (
    "قالبُ هذا التقرير لا يطابق استمارةَ الوزارة المطبوعة لدور الموظّف — المادة 15: «وفقاً "
    "للنماذج المعتمدة من الوزير» (02_staff_affairs.md:199). يُصحَّح بـ"
    "seed_quality_templates --apply، فإن بقي مقفلاً بتقريرٍ معتمَد فالأمرُ للمالك."
)


def form_template_ok(evaluation: EmployeeEvaluation) -> bool:
    """أمربوطٌ بقالبٍ هو استمارةُ دوره المطبوعة؟ (`RoleEvaluationTemplate.matches_ministry_form`)."""
    template = evaluation.template if evaluation.template_id is not None else None
    return template is not None and template.matches_ministry_form()


def is_school_principal(school: School, user: CustomUser) -> bool:
    """
    ألَه عضويّةٌ نشطةٌ بدور المدير في هذه المدرسة — أيّاً كانت عضويّاتُه الأخرى. كان الفحصُ
    على `.first()` بلا ترتيب، فمديرٌ له عضويّةُ معلّمٍ أو وليّ أمرٍ يفلت منه.
    """
    return Membership.objects.filter(
        school=school, user=user, is_active=True, role__name="principal"
    ).exists()


def placement_rejection(school: School, evaluator: CustomUser, employee: CustomUser) -> str | None:
    """
    نصُّ الرفض إن لم يكن `evaluator` الرئيسَ المباشرَ لـ`employee` (ولا المديرَ)، وإلّا None.
    المادة 16 وبطاقاتُ الوصف الوظيفيّ: `quality/reporting_lines.py`.
    """
    if evaluator.is_superuser:
        return None
    roles = get_school_roles(school, evaluator)
    employee_role = get_employee_role(school, employee)
    if may_place(roles, employee_role):
        return None
    return rejection_reason(employee_role)


def is_academic_year(value: str) -> bool:
    """«2026-2027» — عامان متتاليان. غيرُه يُكتب تحت عامٍ لا تقرؤه شاشةٌ ولا يُفحص فيه جزاء."""
    match = _ACADEMIC_YEAR.match(value or "")
    if match is None:
        return False
    return int(match.group(2)) == int(match.group(1)) + 1


@dataclass(frozen=True)
class AppraisalYearFacts:
    """
    وقائعُ «العام الذي يوضع عنه التقرير» التي تقيّد المستوى. تُبنى من سجلّاتها
    (الجزاءات 2.1، والحضور، والتدريب، والرخص) — وكلُّ حقلٍ كما سمّاه النصّ.
    """

    #: أطولُ جزاءٍ تأديبيٍّ مفرد بالخصم من الراتب أو الوقف عن العمل، بالأيّام.
    longest_sanction_days: int = 0
    #: «مجموعها» — أيّامُ الجزاءات بالخصم أو الوقف خلال العام. هل تُجمع أيّامُ الخصم مع
    #: أيّام الوقف أم يُعدّ كلُّ نوعٍ وحده؟ النصُّ لا يصرّح؛ فالجمعُ قرارُ بانيه (ADR-0002 §6.6).
    sanction_days_total: int = 0
    #: «أي جزاء آخر أشد» — ترتيبُه في المادتين 85 و89 من قانون الموارد البشرية المدنية
    #: (تُحيل إليهما المادة 33)، وليسا في مجلّد المصادر؛ فلا قائمةَ من عندنا.
    harsher_sanction: bool = False
    #: أيّامُ الانقطاع عن العمل بدون عذرٍ مقبول.
    unexcused_absence_days: int = 0
    #: المادة 17 (1): أُتيحت له فرصةُ تدريبٍ ولم يجتزه بنجاح.
    training_not_passed: bool = False
    #: المادة 18 (1): أُتيحت له فرصةُ التدريب وتخلّف عنه دون عذرٍ مقبول.
    training_skipped_without_excuse: bool = False
    #: المادة 19 (صفحة الملفّ 12): «أو لم يقم بتجديدها، بمستوى ضعيف» — رخصتُه المهنيّة انقضت
    #: صلاحيّتُها (خمس سنوات من الإصدار — «05- سياسة الرخص المهنية للمعلمين و قادة
    #: المدارس.pdf» ص22) ولم تُجدَّد — النصُّ على وقوع التجديد لا على طلبه.
    #: ومن تقدّم لمستوىً أعلى ولم يُمنحه ليس مستثنى: ص22 بند 4 «لن يفقدوا رخصهم ... ويتعين عليهم
    #: تجديد رخصهم بنفس المستوى في نهاية السنة الخامسة» — فإن لم يجدّد فهو «لم يقم بتجديدها».
    #: أمّا النائبُ الذي تقدّم للتجديد ولم يستوفِ شروطه («لن يفقد» رخصته، ص23 بند 1) فالسياسةُ
    #: صامتةٌ عن أثره في التقييم — سؤالٌ للمالك (ADR-0002 §6.6 بند 4)، ولا يُحسم هنا.
    #: و«لم يحصل عليها» مهلتُها نهاية 2029-2030 (ص7) فلا أثرَ لها على تقييم 2026-2027.
    license_expired_not_renewed: bool = False
    #: سياسة الرخص ص10: معلّمٌ لم تُمنح له الرخصةُ لأنّ أداءه الصفّيّ دون المستوى المتقدَّم
    #: له، «في حال استمرار الأداء المتدني» — لا «جيد جداً» ولا «ممتاز». وتعريفُ «الاستمرار»
    #: للمالك، فالعلامةُ يُدخلها المقيِّم ولا تُشتقّ.
    teacher_license_denied_persistent_low: bool = False


@dataclass(frozen=True)
class RatingRestriction:
    barred: frozenset[str]
    reason: str


def restrictions_for(facts: AppraisalYearFacts) -> list[RatingRestriction]:
    """كلُّ قيدٍ منطبقٍ على الوقائع، بسببه ومادّته — الأشدُّ أوّلاً."""
    found: list[RatingRestriction] = []

    def add(barred: frozenset[str], reason: str) -> None:
        found.append(RatingRestriction(barred, reason))

    if facts.license_expired_not_renewed:
        add(_ALL_BUT_WEAK, "لم يجدّد رخصتَه المهنيّة بعد انقضاء صلاحيّتها، فمستواه «ضعيف» — المادة 19")
    # المادة 18 — تحجب «ممتاز» و«جيد جداً».
    if facts.longest_sanction_days > ART18_SINGLE_SANCTION_DAYS:
        add(_EXCELLENT_OR_VERY_GOOD, "جزاءٌ تأديبيٌّ بالخصم أو الوقف يزيد على عشرة أيام — المادة 18")
    if facts.sanction_days_total > ART18_SANCTION_DAYS_TOTAL:
        add(_EXCELLENT_OR_VERY_GOOD, "جزاءاتٌ يجاوز مجموعها خمسة عشر يوماً خلال العام — المادة 18")
    if facts.harsher_sanction:
        add(_EXCELLENT_OR_VERY_GOOD, "جزاءٌ أشدُّ من الخصم والوقف — المادتان 17 و18")
    if facts.unexcused_absence_days > ART18_UNEXCUSED_ABSENCE_DAYS:
        add(_EXCELLENT_OR_VERY_GOOD, "انقطاعٌ بدون عذرٍ مقبول يزيد على عشرة أيام — المادة 18")
    if facts.training_skipped_without_excuse:
        add(_EXCELLENT_OR_VERY_GOOD, "تخلّف عن تدريبٍ أُتيح له دون عذرٍ مقبول — المادة 18")
    if facts.teacher_license_denied_persistent_low:
        add(
            _EXCELLENT_OR_VERY_GOOD,
            "لم تُمنح له الرخصةُ المهنيّة واستمرّ أداؤه متدنّياً — سياسة الرخص المهنيّة ص10",
        )
    # المادة 17 — تحجب «ممتاز» وحده.
    if ART17_SINGLE_SANCTION_DAYS < facts.longest_sanction_days <= ART18_SINGLE_SANCTION_DAYS:
        add(_EXCELLENT, "جزاءٌ تأديبيٌّ بالخصم أو الوقف يزيد على خمسة أيام — المادة 17")
    if ART17_SANCTION_DAYS_TOTAL < facts.sanction_days_total <= ART18_SANCTION_DAYS_TOTAL:
        add(_EXCELLENT, "جزاءاتٌ يجاوز مجموعها عشرة أيام خلال العام — المادة 17")
    if ART17_UNEXCUSED_ABSENCE_DAYS < facts.unexcused_absence_days <= ART18_UNEXCUSED_ABSENCE_DAYS:
        add(_EXCELLENT, "انقطاعٌ بدون عذرٍ مقبول يزيد على خمسة أيام — المادة 17")
    if facts.training_not_passed:
        add(_EXCELLENT, "أُتيح له تدريبٌ ولم يجتزه بنجاح — المادة 17")
    return found


def ratings_barred_by(facts: AppraisalYearFacts) -> frozenset[str]:
    barred: frozenset[str] = frozenset()
    for restriction in restrictions_for(facts):
        barred |= restriction.barred
    return barred


def year_facts(staff: CustomUser, academic_year: str) -> AppraisalYearFacts | None:
    """
    وقائعُ عام التقرير للموظّف، أو None حين لا سجلَّ يُقرأ منه.

    سجلُّ الجزاءات (2.1، `StaffDisciplinaryAction`) وسجلّا التدريب والرخص لم تُبنَ،
    فالدالّةُ تُرجع None. وهي نقطةُ التعليق الوحيدة: حين تُبنى السجلّاتُ يُقرأ منها هنا.
    """
    return None


def barred_ratings(staff: CustomUser, academic_year: str) -> frozenset[str]:
    """المستوياتُ الممنوعة على الموظّف في عام التقرير — فارغةٌ ما لم توجد وقائع."""
    facts = year_facts(staff, academic_year)
    return ratings_barred_by(facts) if facts is not None else frozenset()


def parse_axis_scores(axes: Sequence[AxisSpec], data: Mapping[str, str]) -> dict[str, int]:
    """درجةُ كلّ محورٍ عددٌ صحيحٌ بين الصفر وحدِّه — وإلّا رُفض التقييم كلُّه."""
    scores: dict[str, int] = {}
    for key, label, max_score in axes:
        raw = (data.get(key) or "0").strip()
        try:
            value = int(raw)
        except ValueError:
            raise EvaluationRejectedError(f"«{label}»: الدرجةُ عددٌ صحيح") from None
        if not 0 <= value <= max_score:
            raise EvaluationRejectedError(f"«{label}»: الدرجةُ بين 0 و{max_score}")
        scores[key] = value
    return scores


def _uses_default_axes(axes: Sequence[AxisSpec]) -> bool:
    return {key for key, _label, _max in axes} <= DEFAULT_AXIS_FIELDS


def _weighted_total(
    evaluation: EmployeeEvaluation, evaluator: CustomUser, own_total: int
) -> Fraction:
    """
    المجموعُ المرجَّح **غير المقرَّب** كما يحسبه `calculate_weighted_total` — بدرجات هذا
    المقيِّم الجديدة. التقريبُ للعرض وحده؛ والتصنيفُ على هذا (المادة 16، `rating_for`).
    """
    own_weight = 100
    pairs: list[tuple[int, int]] = []
    for score in evaluation.scores.all():
        if score.evaluator_id == evaluator.pk:
            own_weight = score.weight
        else:
            pairs.append((score.total_score, score.weight))
    pairs.append((own_total, own_weight))
    total_weight = sum(w for _t, w in pairs)
    if not total_weight:
        return Fraction(own_total)
    return Fraction(sum(t * w for t, w in pairs), total_weight)


@transaction.atomic
def save_evaluation(
    *,
    evaluation: EmployeeEvaluation,
    evaluator: CustomUser,
    axes: Sequence[AxisSpec],
    data: Mapping[str, str],
) -> EmployeeEvaluation:
    """
    يحفظ درجاتِ المقيِّم وملاحظاتِه وحالةَ التقييم، أو يرفع `EvaluationRejectedError`
    ولا يكتب شيئاً.

    المحاورُ الافتراضيّةُ الأربعة حقولٌ على التقييم نفسه. ومحاورُ قالب الدور
    (الاستمارات الوزاريّة) لا حقولَ لها، فتُحفظ في `EvaluationScore.custom_axes`
    لهذا المقيِّم، ويُحسب المجموعُ مرجَّحاً على المقيِّمين — وكانت تُرمى قبل ذلك
    فيُحفظ التقييمُ صفراً.
    """
    status = data.get("action", "draft")
    if status not in _EVALUATOR_STATUSES:
        raise EvaluationRejectedError("حالةُ التقييم مسودّةٌ أو مُقدَّمٌ فقط")
    if not evaluation._state.adding:
        # القفلُ قبل كلّ قراءة: الحالةُ ودرجاتُ المقيِّمين الآخرين تُقرأ بعد أن يُمسك الصفّ،
        # فلا يكتب حفظٌ بنسخةٍ قُرئت قبل الاعتماد فوقه، ولا يحسب مقيِّمان من درجةٍ قديمة.
        EmployeeEvaluation.objects.select_for_update().filter(pk=evaluation.pk).exists()
        evaluation.refresh_from_db()
    if evaluation.status in _LOCKED_STATUSES:
        raise EvaluationRejectedError("التقريرُ معتمَد — لا تُعدَّل درجاتُه بعد اعتماد المدير.")
    if is_school_principal(evaluation.school, evaluation.employee):
        raise EvaluationRejectedError(PRINCIPAL_NOT_EVALUATED)
    if evaluation.employee_id == evaluator.pk:
        raise EvaluationRejectedError(SELF_EVALUATION)
    rejected = placement_rejection(evaluation.school, evaluator, evaluation.employee)
    if rejected is not None:
        raise EvaluationRejectedError(rejected)
    # المادة 16: «يضع الرئيس المباشر تقييم أداء الموظف ويعتمد من مدير المدرسة» — واضعٌ واحد.
    # كان كلُّ من يضغط حفظاً (المديرُ يفتح التقرير ليعتمده) يصير مقيِّماً ثانياً بدرجاتٍ
    # صفريّة ووزن 100، فينقسم المجموع ويُستبدل الواضع.
    if evaluation.has_saved_content() and evaluation.evaluator_id != evaluator.pk:
        raise EvaluationRejectedError(
            f"وضعُ هذا التقرير لواضعه ({evaluation.evaluator.full_name}) — المادة 16."
        )
    if evaluation.period == EmployeeEvaluation.MINISTRY_PERIOD and _uses_default_axes(axes):
        raise EvaluationRejectedError(
            "التقريرُ السنويّ يوضع على استمارة الوزارة لدور الموظّف، ولا استمارةَ له هنا — "
            "المادة 15: «وفقاً للنماذج المعتمدة من الوزير» (02_staff_affairs.md:199)."
        )
    # والقالبُ نفسُه استمارةُ دوره كما طُبعت (`matches_ministry_form`): مسودّةٌ عليها درجاتٌ
    # تبقى على قالبها، فإن خرج عن الاستمارة بعدها كان تقديمُها يُقبل ولا يُعتمد أبداً.
    if evaluation.period == EmployeeEvaluation.MINISTRY_PERIOD and not form_template_ok(evaluation):
        raise EvaluationRejectedError(TEMPLATE_OFF_FORM)
    scores = parse_axis_scores(axes, data)

    if _uses_default_axes(axes):
        for key, value in scores.items():
            setattr(evaluation, key, value)
        evaluation.calculate_total()
    else:
        exact = _weighted_total(evaluation, evaluator, sum(scores.values()))
        evaluation.total_score = EmployeeEvaluation.total_for(exact)
        evaluation.rating = EmployeeEvaluation.rating_for(exact)
        # الدرجاتُ تُكتب قبل الحكم على المستوى: صفُّ مقيِّمٍ آخر بمفاتيحَ غيرِ مفاتيح الاستمارة
        # يُبقي التقريرَ السنويَّ بلا اسمِ مستوى (`_drop_level_off_form`، ومستنده المادة 15
        # في 02_staff_affairs.md:199). وإن رُفض الحفظُ بعدها فالمعاملةُ ترجع كلُّها.
        EvaluationScore.objects.update_or_create(
            evaluation=evaluation, evaluator=evaluator, defaults={"custom_axes": scores}
        )
        evaluation.settle_level_after_scores()

    _enforce_rating_restrictions(evaluation)

    evaluation.strengths = data.get("strengths", "")
    evaluation.improvements = data.get("improvements", "")
    evaluation.goals_next = data.get("goals_next", "")
    evaluation.status = status
    evaluation.evaluator = evaluator

    if _uses_default_axes(axes):
        evaluation.save()
        return evaluation

    # `update_fields` بلا حقول المحاور الافتراضيّة: فلا يُعيد `save()` الحسابَ منها
    # فيمحو المجموعَ المرجَّح.
    evaluation.save(
        update_fields=[
            "total_score",
            "rating",
            "strengths",
            "improvements",
            "goals_next",
            "status",
            "evaluator",
            "updated_at",
        ]
    )
    return evaluation


def _enforce_rating_restrictions(evaluation: EmployeeEvaluation) -> None:
    """
    قيودُ المواد 17–19 على التقرير السنويّ الوزاريّ (S2) وحده: المتابعةُ الداخليّة (S1)
    لا سندَ وزاريَّ لها.

    المستوى الممنوع يُرفض ولا يُخفَّض صامتاً — الخفضُ يُبقي درجةً لا تطابق مستواها،
    والمقيِّمُ هو من يضع الدرجة (المادة 16). وهذا اختيارٌ هندسيٌّ لا حكمٌ وزاريّ.
    """
    if evaluation.period != EmployeeEvaluation.MINISTRY_PERIOD:
        return
    facts = year_facts(evaluation.employee, evaluation.academic_year)
    if facts is None:
        return
    for restriction in restrictions_for(facts):
        if evaluation.rating in restriction.barred:
            raise EvaluationRejectedError(
                f"لا يجوز مستوى «{evaluation.get_rating_display()}»: {restriction.reason}."
            )


@transaction.atomic
def approve_evaluation(*, evaluation: EmployeeEvaluation, approver: CustomUser) -> None:
    """
    اعتمادُ التقرير: «يضع الرئيس المباشر تقييم أداء الموظف ويعتمد من مدير المدرسة»
    (المادة 16، `02_staff_affairs.md:200`؛ القرار 32/2019 صفحة الملفّ 10). فالاعتمادُ
    لمدير المدرسة وحده، لتقريرٍ مُقدَّم، وتُعاد فيه قيودُ المواد 17–19 — فالوقائعُ قد
    تتغيّر بين التقديم والاعتماد.
    """
    locked = EmployeeEvaluation.objects.select_for_update().get(pk=evaluation.pk)
    if not is_school_principal(locked.school, approver):
        raise EvaluationRejectedError("الاعتمادُ لمدير المدرسة وحده — المادة 16.")
    if locked.status != "submitted":
        raise EvaluationRejectedError("لا يُعتمد إلّا تقريرٌ مُقدَّم.")
    if locked.employee_id == approver.pk or is_school_principal(locked.school, locked.employee):
        raise EvaluationRejectedError(PRINCIPAL_NOT_EVALUATED)
    # العبرةُ بموضع الدرجات: درجاتُ الاستمارة لا تُحفظ إلّا عند واضعها (`EvaluationScore`).
    # فصفٌّ مربوطٌ بقالبٍ بلا درجةٍ عند أحد — درجاتُه في المحاور الأربعة (ربطُ الـGET القديم)،
    # أو صفرٌ رُميت درجاتُه في المسار القديم — مجموعُه من غير الاستمارة، فلا يُعتمد كما لا
    # يُعتمد غيرُ المربوط؛ وكان الصفرُ يُعتمد «ضعيفاً».
    # ومفاتيحُها مفاتيحُ محاور القالب بعينها (`has_form_scores`): صفٌّ أُدخلت درجاتُه من لوحة
    # الإدارة بمفاتيحَ أخرى كان يُعتمد بمجموعٍ لا صلةَ له بالاستمارة.
    if locked.period == EmployeeEvaluation.MINISTRY_PERIOD and not locked.has_form_scores():
        raise EvaluationRejectedError(
            "لا يُعتمد تقريرٌ سنويٌّ على غير استمارة الوزارة — المادة 15: «وفقاً للنماذج "
            "المعتمدة من الوزير» (02_staff_affairs.md:199)."
        )
    _enforce_rating_restrictions(locked)
    locked.status = "approved"
    # لحظةُ الاعتماد تُخزَّن: منها يُعلم الموظّفُ، فلا يسبقها تاريخُ الاستلام (المادة 20).
    locked.approved_at = timezone.now()
    locked.save(update_fields=["status", "approved_at", "updated_at"])
    evaluation.status = locked.status
    evaluation.approved_at = locked.approved_at


@transaction.atomic
def record_receipt_on_refusal(
    *, evaluation: EmployeeEvaluation, recorder: CustomUser, received_on: date
) -> None:
    """
    «تاريخ استلام الموظف (يرجى تدوين التاريخ في حالة رفض الموظف التوقيع)» — «استمارة تقييم
    المعلم والدليل التفسيري.pdf» ص2. يدوّنه مدير المدرسة الموقِّعُ على الاستمارة، فيكون
    «تاريخ علمه» الذي تبدأ منه مهلةُ التظلّم (المادة 20). وكان الإقرارُ وحدَه يبدأها، فرفضُ
    الموظّف الإقرارَ يُبقي التقريرَ غيرَ نهائيٍّ أبداً.
    """
    locked = EmployeeEvaluation.objects.select_for_update().get(pk=evaluation.pk)
    if not is_school_principal(locked.school, recorder):
        raise EvaluationRejectedError("تدوينُ تاريخ الاستلام لمدير المدرسة — موقِّعِ الاستمارة.")
    if locked.status != "approved" or locked.acknowledged_at is not None:
        raise EvaluationRejectedError("يُدوَّن تاريخُ الاستلام لتقريرٍ معتمَدٍ لم يُقرّ به الموظّف.")
    if locked.received_on is not None:
        raise EvaluationRejectedError("تاريخُ الاستلام مدوَّنٌ من قبل.")
    if received_on > timezone.localdate():
        raise EvaluationRejectedError("تاريخُ الاستلام لا يكون في المستقبل.")
    # ولا يسبق الاعتماد: «يُعلن الموظف بنسخة من تقرير تقييم الأداء» بعد اعتماده، والمهلةُ
    # «من تاريخ علمه» (المادة 20). فتاريخٌ قبله كان يجعل التقريرَ نهائيّاً فورَ تدوينه
    # ويحرم الموظّفَ الخمسةَ عشرَ يوماً. وصفوفُ ما قبل الحقل: حدُّها لحظةُ إنشاء التقرير.
    approved_on = timezone.localtime(locked.approved_at or locked.created_at).date()
    if received_on < approved_on:
        raise EvaluationRejectedError(
            f"تاريخُ الاستلام لا يسبق اعتماد التقرير ({approved_on}) — المادة 20."
        )
    locked.received_on = received_on
    locked.save(update_fields=["received_on", "updated_at"])
    evaluation.received_on = received_on


@dataclass(frozen=True)
class AnnualRatingSummary:
    """أرقامُ شريط اللوحة — كلُّها على مجموعةٍ واحدة من التقارير السنويّة."""

    #: متوسّطُ `total_score` لتلك التقارير، أو None إن لم يكن منها شيء.
    average: float | None
    #: عددُها بكلّ مستوىً من مستويات المادة 16.
    levels: dict[str, int]


def annual_rating_summary(school: School, academic_year: str) -> AnnualRatingSummary:
    """
    التقاريرُ السنويّة الموضوعة فعلاً: لا المسودّات، ولا متابعة S1 الداخليّة، ولا صفَّ S2 ليس
    على الاستمارة (`has_form_scores`) — فذاك لا مستوى وزاريَّ له (المادة 15: «وفقاً للنماذج
    المعتمدة من الوزير»، 02_staff_affairs.md:199). والمتوسّطُ على المجموعة نفسها التي يُعدّ
    توزيعُها بجواره: كان يخلط S1 بـS2 فيعدّ الموظّفَ مرّتين ويخالف التوزيع.
    """
    rows = (
        EmployeeEvaluation.objects.filter(
            school=school,
            academic_year=academic_year,
            period=EmployeeEvaluation.MINISTRY_PERIOD,
            status__in=["submitted", "approved", "acknowledged"],
            template__isnull=False,
        )
        .exclude(rating="")
        .select_related("template")
        .prefetch_related("scores", "template__axes")
    )
    counted = [row for row in rows if row.has_form_scores()]
    average = round(sum(row.total_score for row in counted) / len(counted), 1) if counted else None
    return AnnualRatingSummary(average=average, levels=dict(Counter(row.rating for row in counted)))


def axis_values(
    evaluation: EmployeeEvaluation, evaluator: CustomUser, axes: Sequence[AxisSpec]
) -> dict[str, int]:
    """
    قيمُ المحاور المعروضة في النموذج: من الحقول، أو من درجات `evaluator` في القالب. والعرضُ
    يمرّر واضعَ التقرير لا فاتحَه — كان المديرُ يرى محاورَ تقريرٍ مُقدَّمٍ أصفاراً.
    """
    if _uses_default_axes(axes):
        return {key: getattr(evaluation, key) or 0 for key, _l, _m in axes}
    own = evaluation.scores.filter(evaluator=evaluator).first() if evaluation.pk else None
    custom = own.custom_axes if own else {}
    return {key: int(custom.get(key, 0)) for key, _l, _m in axes}


def save_evaluation_form(
    *,
    school: School,
    employee: CustomUser,
    year: str,
    period: str,
    existing: EmployeeEvaluation | None,
    template: RoleEvaluationTemplate | None,
    axes: Sequence[AxisSpec],
    evaluator: CustomUser,
    data: Mapping[str, str],
) -> EmployeeEvaluation:
    """
    الإنشاءُ وربطُ القالب والحفظُ معاملةٌ واحدة: الطلبُ المرفوض (`EvaluationRejectedError`)
    لا يترك مسودّةً. كانت في `create_evaluation` (العرض) فتجاوزت سقفَ الطبقات.
    """
    with transaction.atomic():
        obj = existing or EmployeeEvaluation(
            school=school,
            employee=employee,
            academic_year=year,
            period=period,
            evaluator=evaluator,
        )
        if obj.template_id != (template.pk if template else None):
            obj.template = template
            if not obj._state.adding:
                obj.save(update_fields=["template"])
        if obj._state.adding:
            obj.save()
        save_evaluation(evaluation=obj, evaluator=evaluator, axes=axes, data=data)
    return obj
