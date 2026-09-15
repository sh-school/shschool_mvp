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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from core.models import Membership

from .models import EmployeeEvaluation, EvaluationScore

if TYPE_CHECKING:
    from core.models import CustomUser, School

#: (مفتاح المحور، اسمه، درجته القصوى) — كما يبنيها `_get_axes_for_employee`.
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


#: «وتتولى لجنة شؤون المدارس تقييم أداء مديري المدارس سنوياً» — المادة 16،
#: «02- النظام الوظيفي لموظفي المدارس.pdf» صفحة الملفّ 10 (02_staff_affairs.md:199).
PRINCIPAL_NOT_EVALUATED = (
    "تقييمُ مدير المدرسة للجنة شؤون المدارس لا للمدرسة — المادة 16 (02_staff_affairs.md:199)"
)


def is_school_principal(school: School, user: CustomUser) -> bool:
    """
    ألَه عضويّةٌ نشطةٌ بدور المدير في هذه المدرسة — أيّاً كانت عضويّاتُه الأخرى. كان الفحصُ
    على `.first()` بلا ترتيب، فمديرٌ له عضويّةُ معلّمٍ أو وليّ أمرٍ يفلت منه.
    """
    return Membership.objects.filter(
        school=school, user=user, is_active=True, role__name="principal"
    ).exists()


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
    #: المادة 19: رخصتُه المهنيّة انقضت صلاحيّتُها (خمس سنوات من الإصدار — «05- سياسة
    #: الرخص المهنية للمعلمين و قادة المدارس.pdf» ص22) ولم يتقدّم لتجديدها. أمّا «لم يحصل
    #: عليها» فمهلتُها نهاية 2029-2030 (ص7) فلا أثرَ لها على تقييم 2026-2027. ولا يُعدّ هنا
    #: من نصّت السياسةُ على احتفاظه برخصته (ص22 بند 4، ص23–24).
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
    # المادة 16: «يضع الرئيس المباشر تقييم أداء الموظف ويعتمده مدير المدرسة» — واضعٌ واحد.
    # كان كلُّ من يضغط حفظاً (المديرُ يفتح التقرير ليعتمده) يصير مقيِّماً ثانياً بدرجاتٍ
    # صفريّة ووزن 100، فينقسم المجموع ويُستبدل الواضع.
    if evaluation.has_saved_content() and evaluation.evaluator_id != evaluator.pk:
        raise EvaluationRejectedError(
            f"وضعُ هذا التقرير لواضعه ({evaluation.evaluator.full_name}) — المادة 16."
        )
    if evaluation.period == EmployeeEvaluation.MINISTRY_PERIOD and _uses_default_axes(axes):
        raise EvaluationRejectedError(
            "التقريرُ السنويّ يوضع على استمارة الوزارة لدور الموظّف، ولا استمارةَ له هنا — "
            "المادة 16: «وفقاً للنماذج المعتمدة من الوزير» (02_staff_affairs.md:199)."
        )
    scores = parse_axis_scores(axes, data)

    if _uses_default_axes(axes):
        for key, value in scores.items():
            setattr(evaluation, key, value)
        evaluation.calculate_total()
    else:
        exact = _weighted_total(evaluation, evaluator, sum(scores.values()))
        evaluation.total_score = EmployeeEvaluation.total_for(exact)
        evaluation.rating = EmployeeEvaluation.rating_for(exact)

    _enforce_rating_restrictions(evaluation)

    evaluation.strengths = data.get("strengths", "")
    evaluation.improvements = data.get("improvements", "")
    evaluation.goals_next = data.get("goals_next", "")
    evaluation.status = status
    evaluation.evaluator = evaluator

    if _uses_default_axes(axes):
        evaluation.save()
        return evaluation

    EvaluationScore.objects.update_or_create(
        evaluation=evaluation, evaluator=evaluator, defaults={"custom_axes": scores}
    )
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
    اعتمادُ التقرير: «يضع الرئيس المباشر تقييم أداء الموظف ويعتمده مدير المدرسة»
    (المادة 16، `02_staff_affairs.md:200`؛ القرار 32/2019 صفحة الملفّ 10). فالاعتمادُ
    لمدير المدرسة وحده، لتقريرٍ مُقدَّم، وتُعاد فيه قيودُ المواد 17–19 — فالوقائعُ قد
    تتغيّر بين التقديم والاعتماد.
    """
    if approver.role != "principal":
        raise EvaluationRejectedError("الاعتمادُ لمدير المدرسة وحده — المادة 16.")
    locked = EmployeeEvaluation.objects.select_for_update().get(pk=evaluation.pk)
    if locked.status != "submitted":
        raise EvaluationRejectedError("لا يُعتمد إلّا تقريرٌ مُقدَّم.")
    if locked.employee_id == approver.pk or is_school_principal(locked.school, locked.employee):
        raise EvaluationRejectedError(PRINCIPAL_NOT_EVALUATED)
    if locked.period == EmployeeEvaluation.MINISTRY_PERIOD and locked.template_id is None:
        raise EvaluationRejectedError(
            "لا يُعتمد تقريرٌ سنويٌّ على غير استمارة الوزارة — المادة 16: «وفقاً للنماذج "
            "المعتمدة من الوزير» (02_staff_affairs.md:199)."
        )
    _enforce_rating_restrictions(locked)
    locked.status = "approved"
    locked.save(update_fields=["status", "updated_at"])
    evaluation.status = locked.status


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
    if recorder.role != "principal":
        raise EvaluationRejectedError("تدوينُ تاريخ الاستلام لمدير المدرسة — موقِّعِ الاستمارة.")
    locked = EmployeeEvaluation.objects.select_for_update().get(pk=evaluation.pk)
    if locked.status != "approved" or locked.acknowledged_at is not None:
        raise EvaluationRejectedError("يُدوَّن تاريخُ الاستلام لتقريرٍ معتمَدٍ لم يُقرّ به الموظّف.")
    if locked.received_on is not None:
        raise EvaluationRejectedError("تاريخُ الاستلام مدوَّنٌ من قبل.")
    if received_on > timezone.localdate():
        raise EvaluationRejectedError("تاريخُ الاستلام لا يكون في المستقبل.")
    locked.received_on = received_on
    locked.save(update_fields=["received_on", "updated_at"])
    evaluation.received_on = received_on


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
