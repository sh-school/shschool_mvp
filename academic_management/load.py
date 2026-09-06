"""حملُ المعلّم بصيغةٍ واحدةٍ — تُستعمل في كلّ موضعٍ ولا تُعاد كتابتُها.

    TeachingLoad     = ∑ weekly_periods   (الإسناداتُ النشطة)
    PreparationLoad  = PreparedCourses × preparation_weight   (تُعرض ولا تُحتسب)
    TotalLoad        = TeachingLoad + PreparationLoad
    Preparations     = |{(grade, track, subject)}|   أزواجٌ متمايزةٌ يدرّسها

والعرضُ في كلّ شاشةٍ بالصيغة نفسها: «14 تدريس + 4 تحضير (مقرّران) = 18 من 18».

ولماذا وحدةٌ مستقلّة؟ لأنّ الرقمَ يظهر في اللوحة الجانبيّة وعمودِ الشبكة
وميزانِ القسم وكشفِ المعلّم وإشعارِه — خمسةُ مواضع، ولو حُسب في كلٍّ منها
لاختلف يوماً عن أخيه بحصّةٍ فلا يُعرف أيُّهما الصواب.

والهدفُ الذي يُقارَن به يأتي من خطّة نصابٍ معتمَدة، وإلّا من النصاب المرجعيّ
في الحوكمة، وإلّا فلا مقارنة. **ولا يُخترع رقم.**
"""

from collections import defaultdict
from dataclasses import dataclass, field

from academic_management.models import (
    FROZEN_STATUSES,
    CoursePreparation,
    TeacherWorkloadPlan,
    WorkloadGovernance,
)

#: من أين جاء الهدف — تُعرض مع الرقم كي لا يُقرأ المرجعيُّ معتمَداً.
FROM_APPROVED_PLAN = "approved_plan"
#: نصابٌ كُتب في شاشة الإسناد ولم يُعتمد بعد — يُقاس إليه ويُقال إنّه مسودّة.
FROM_DRAFT_PLAN = "draft_plan"
FROM_REFERENCE = "reference_load"
NO_TARGET = ""


@dataclass
class TeacherLoad:
    teacher_id: object
    teaching: int = 0
    prepared_courses: int = 0
    preparation_weight: int = 2
    preparations_taught: int = 0
    target: int | None = None
    target_source: str = NO_TARGET
    courses: set = field(default_factory=set)

    @property
    def preparation(self) -> int:
        return self.prepared_courses * self.preparation_weight

    @property
    def total(self) -> int:
        """النصابُ حصصُ التدريس وحدَها — والتحضيرُ عرفاً لا يُسجَّل فيه.

        قرارُ الإدارة (2026-09-06): حصّتا التحضير مسؤوليّةٌ تُسجَّل وتظهر في
        كشف المعلّم، ولا تدخل في نصابه. وكانتا تُضافان إليه فيظهر من يدرّس
        ثمانيةَ عشرَ ويحضّر مقرّرين متجاوزاً نصابَه باثنتين — تجاوزٌ لا وجودَ
        له في العرف الذي تعمل به المدرسة.

        و`preparation` باقيةٌ للعرض: تقول كم حصّةً يساوي التحضيرُ عرفاً، لا
        كم يضيف إلى النصاب.
        """
        return self.teaching

    @property
    def delta(self) -> int | None:
        """الفرقُ عن الهدف — و`None` حين لا هدفَ يُقارَن به."""
        return None if self.target is None else self.total - self.target

    @property
    def over_target(self) -> bool:
        return self.delta is not None and self.delta > 0

    def label(self) -> str:
        """«18 تدريس من 18 · تحضير: مقرّران» — والهدفُ يُذكر إن وُجد."""
        text = f"{self.teaching} تدريس"
        if self.target is not None:
            text += f" من {self.target}"
        if self.prepared_courses:
            text += f" · تحضير: {_course_noun(self.prepared_courses)}"
        return text


def _course_noun(n: int) -> str:
    if n == 1:
        return "مقرّرٌ واحد"
    if n == 2:
        return "مقرّران"
    if 3 <= n <= 10:
        return f"{n} مقرّرات"
    return f"{n} مقرّراً"


def targets_for(school, academic_year):
    """هدفُ كلّ معلّمٍ ومصدرُه — خطّةٌ معتمَدة، وإلّا المرجعيّ، وإلّا لا شيء."""
    governance = WorkloadGovernance.for_school(school)
    fallback = governance.reference_load
    out = {}
    approved = TeacherWorkloadPlan.objects.filter(
        school=school, academic_year=academic_year, status__in=FROZEN_STATUSES
    ).order_by("teacher_id", "-plan_version")
    for plan in approved:
        out.setdefault(plan.teacher_id, (plan.teaching_target, FROM_APPROVED_PLAN))
    # قرارُ 2026-09-06: النصابُ رقمٌ واحدٌ يُكتب في شاشة الإسناد ويُقاس إليه من
    # فوره — والاعتمادُ لاحقٌ لا شرطٌ للقياس.
    drafts = TeacherWorkloadPlan.objects.filter(
        school=school, academic_year=academic_year
    ).exclude(status__in=FROZEN_STATUSES).order_by("teacher_id", "-plan_version")
    for plan in drafts:
        out.setdefault(plan.teacher_id, (plan.teaching_target, FROM_DRAFT_PLAN))
    return out, fallback, governance.preparation_weight


def loads_for(school, academic_year, assignments=None, preparations=None):
    """حملُ كلّ معلّمٍ في المدرسة — بأربعة استعلاماتٍ مهما كثر المعلّمون.

    `assignments` و`preparations` تُمرَّران محمَّلتين حين تكون الشاشةُ قد قرأتهما،
    وإلّا قُرئتا هنا. والقراءةُ مرّةً واحدةً شرطُ ألّا يصير الحمل N+1.
    """
    from operations.models import SubjectClassAssignment

    if assignments is None:
        assignments = list(
            SubjectClassAssignment.objects.live(school, year=academic_year)
            .filter(teacher__isnull=False)
            .select_related("class_group")
        )
    if preparations is None:
        preparations = list(CoursePreparation.objects.live(school, year=academic_year))

    targets, fallback, weight = targets_for(school, academic_year)

    loads: dict = {}
    for a in assignments:
        load = loads.setdefault(
            a.teacher_id, TeacherLoad(teacher_id=a.teacher_id, preparation_weight=weight)
        )
        load.teaching += a.weekly_periods
        load.courses.add((a.class_group.grade, a.class_group.track, a.subject_id))

    for p in preparations:
        load = loads.setdefault(
            p.teacher_id, TeacherLoad(teacher_id=p.teacher_id, preparation_weight=weight)
        )
        load.prepared_courses += 1

    for teacher_id, load in loads.items():
        load.preparations_taught = len(load.courses)
        if teacher_id in targets:
            load.target, load.target_source = targets[teacher_id]
        elif fallback is not None:
            load.target, load.target_source = fallback, FROM_REFERENCE
    return loads


def load_for(school, academic_year, teacher_id):
    """حملُ معلّمٍ واحد — يمرّ من الحساب الجماعيّ كي لا توجد صيغتان.

    ومن لا إسنادَ له بعدُ يُعاد بحملٍ صفرٍ **وهدفِه المعروف**، لا بهدفٍ فارغ.
    فأوّلُ إسنادٍ يُسنَد إليه هو أوّلُ ما يُقاس على هدفه — ولو أُهمل الهدفُ هنا
    لمرّ التجاوزُ الأوّلُ بلا تنبيه، ثمّ ظهر في الثاني بلا تفسير.
    """
    found = loads_for(school, academic_year).get(teacher_id)
    if found is not None:
        return found

    targets, fallback, weight = targets_for(school, academic_year)
    empty = TeacherLoad(teacher_id=teacher_id, preparation_weight=weight)
    if teacher_id in targets:
        empty.target, empty.target_source = targets[teacher_id]
    elif fallback is not None:
        empty.target, empty.target_source = fallback, FROM_REFERENCE
    return empty


def by_department(school, academic_year, loads=None):
    """مجموعُ أحمال كلّ قسمٍ من عضويّات معلّميه — لميزان القسم."""
    from core.models import Membership

    loads = loads if loads is not None else loads_for(school, academic_year)
    out = defaultdict(lambda: {"teaching": 0, "preparation": 0, "teachers": 0})
    memberships = Membership.objects.filter(
        school=school, is_active=True, department_obj__isnull=False
    )
    for m in memberships:
        entry = out[m.department_obj_id]
        entry["teachers"] += 1
        load = loads.get(m.user_id)
        if load:
            entry["teaching"] += load.teaching
            entry["preparation"] += load.preparation
    return dict(out)
