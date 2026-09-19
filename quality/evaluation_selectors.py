"""
quality/evaluation_selectors.py
قراءاتُ شاشات تقييم الأداء — كانت في `evaluation_views.py` فتجاوزت سقفَ الطبقات
(`tests/test_layering.py`): القراءةُ هنا والكتابةُ في `evaluation_services.py`.
"""

from __future__ import annotations

from typing import Any

from core.models import CustomUser, Membership
from core.models.user import role_rank

from .appraisal_forms import forms_by_role
from .models import (
    _EVALUABLE_ROLES,
    EmployeeEvaluation,
    EvaluationCycle,
    RoleEvaluationTemplate,
)

# المحاور الافتراضية (تُستخدم عندما لا يوجد قالب مخصص)
DEFAULT_AXES = [
    ("axis_professional", "الكفاءة المهنية", 25),
    ("axis_commitment", "الالتزام والمسؤولية", 25),
    ("axis_teamwork", "العمل الجماعي والتواصل", 25),
    ("axis_development", "التطوير المهني والمبادرة", 25),
]


def is_active_member(school: Any, user: CustomUser) -> bool:
    return Membership.objects.filter(school=school, user=user, is_active=True).exists()


def get_employee_role(school: Any, employee: CustomUser) -> str | None:
    """
    الدورُ الحاكمُ للموظّف في المدرسة، بترتيب `CustomUser.active_memberships` نفسِه. كان
    `.first()` بلا ترتيب، فصاحبُ العضويّتين يُقيَّم على استمارة أيٍّ منهما اتّفق.
    """
    membership = (
        Membership.objects.filter(school=school, user=employee, is_active=True)
        .select_related("role")
        .order_by(role_rank(), "joined_at", "id")
        .first()
    )
    return membership.role.name if membership else None


def get_axes_for_employee(school: Any, employee: CustomUser, year: str) -> tuple[list, Any]:
    """
    الحصول على محاور التقييم حسب دور الموظف.
    إذا وُجد قالبٌ هو استمارةُ دوره (`matches_ministry_form`) → محاور القالب.
    وإلا → المحاور الأربعة الافتراضية — فلا يُفتح عليها تقريرٌ سنويّ (المادة 15،
    02_staff_affairs.md:199: «وفقاً للنماذج المعتمدة من الوزير»).
    """
    role_name = get_employee_role(school, employee)
    if role_name:
        template = (
            RoleEvaluationTemplate.objects.filter(
                school=school, role_name=role_name, academic_year=year, is_active=True
            )
            .prefetch_related("axes")
            .first()
        )
        if template and template.matches_ministry_form():
            return (
                [(a.key, a.label, a.weight) for a in template.axes.all()],
                template,
            )
    return DEFAULT_AXES, None


def axes_for_evaluation(
    school: Any, employee: CustomUser, year: str, existing: EmployeeEvaluation | None
) -> tuple[list, Any]:
    """
    محاورُ النموذج. تقييمٌ عليه ما يُفقَد (درجاتٌ أو حالةٌ فوق المسودّة) يُعرض على المحاور
    التي حُفظ بها: قالبُه إن كان مربوطاً، وإلّا الافتراضيّةُ الأربعة — ولا يُنقل إلى قالب
    دوره الحاليّ. كان مجرّدُ فتحه بعد بذر القوالب (أو بعد تغيّر دور الموظّف) يربطه بالقالب
    الجديد ويعرض محاوره صفراً، ثمّ يمحو الحفظُ التالي درجاتِه من المجموع.

    والعبرةُ بموضع الدرجات لا بالربط: صفٌّ ربطه الـGET القديمُ بقالبٍ ودرجاتُه في المحاور
    الأربعة (بلا `EvaluationScore`) يُعرض عليها هي، ويُفكّ ربطُه عند الحفظ — فالتقريرُ
    السنويّ عليها يُرفض حينئذٍ بدل أن يُعتمد بمجموعٍ من غير الاستمارة.
    """
    if existing is not None and existing.has_saved_content():
        if (
            existing.template is not None
            and existing.template.axes.exists()
            and not existing.has_default_axis_scores()
        ):
            return [(a.key, a.label, a.weight) for a in existing.template.axes.all()], (
                existing.template
            )
        return DEFAULT_AXES, None
    return get_axes_for_employee(school, employee, year)


def s2_blocked_reason(role_name: str, seeded_roles: set[str]) -> str:
    """
    لماذا لا يُفتح التقريرُ السنويّ لهذا الدور — أو "" إن كان يُفتح. هو ما يردّ به
    `create_evaluation` 409، فيُعرض في الصفّ نصّاً بدل زرٍّ يُفضي إلى صفحةٍ خامّة.
    """
    if role_name in seeded_roles:
        return ""
    if role_name in forms_by_role():
        return "الاستمارة غير مبذورة لهذا العام"
    # المادة 15: «وفقاً للنماذج المعتمدة من الوزير» — ولا استمارةَ مسمّاةً للدور (ADR-0002 §6.6).
    return "لا استمارة وزاريّة للدور — معلّقٌ للمالك"


def get_evaluable_staff(school: Any, year: str, viewer: CustomUser | None = None) -> list[dict]:
    """قائمة الموظفين القابلين للتقييم مع حالة التقييم"""
    memberships = (
        Membership.objects.filter(school=school, is_active=True, role__name__in=_EVALUABLE_ROLES)
        .select_related("user", "role")
        .order_by("role__name", "user__full_name")
    )

    # التقييمات الحالية لهذا العام
    existing_evals = {
        (e.employee_id, e.period): e
        for e in EmployeeEvaluation.objects.filter(
            school=school, academic_year=year
        ).select_related("evaluator")
    }

    # «مبذور» = قالبٌ هو استمارةُ دوره، كما يقرؤه `get_axes_for_employee`.
    seeded_roles = {
        t.role_name
        for t in RoleEvaluationTemplate.objects.filter(
            school=school, academic_year=year, is_active=True
        ).prefetch_related("axes")
        if t.matches_ministry_form()
    }

    staff_list = []
    for m in memberships:
        s1_eval = existing_evals.get((m.user_id, "S1"))
        s2_eval = existing_evals.get((m.user_id, "S2"))
        staff_list.append(
            {
                "user": m.user,
                "role": m.role,
                "role_display": m.role.get_name_display(),
                "s1": s1_eval,
                "s2": s2_eval,
                # المادة 16: «يضع الرئيس المباشر» — فلا زرَّ لتقييم المقيِّم نفسه.
                "is_self": viewer is not None and m.user_id == viewer.pk,
                "s2_blocked": s2_blocked_reason(m.role.name, seeded_roles),
            }
        )
    return staff_list


def get_cycles(school: Any, year: str) -> list[EvaluationCycle]:
    return list(EvaluationCycle.objects.filter(school=school, academic_year=year))


def get_recent_evaluations(school: Any, year: str, limit: int = 20) -> list[EmployeeEvaluation]:
    return list(
        EmployeeEvaluation.objects.filter(school=school, academic_year=year)
        .select_related("employee", "evaluator")
        .order_by("-created_at")[:limit]
    )


def find_evaluation(
    school: Any, employee: CustomUser, year: str, period: str
) -> EmployeeEvaluation | None:
    return (
        EmployeeEvaluation.objects.filter(
            school=school, employee=employee, academic_year=year, period=period
        )
        .select_related("template")
        .first()
    )


def get_scores(evaluation: EmployeeEvaluation) -> list:
    return list(evaluation.scores.select_related("evaluator").all())


def get_published_evaluations(school: Any, employee: CustomUser) -> list[EmployeeEvaluation]:
    """ما يراه الموظّفُ عن نفسه: المعتمَدُ والمُقرّ به فقط."""
    return list(
        EmployeeEvaluation.objects.filter(
            employee=employee, school=school, status__in=["approved", "acknowledged"]
        )
        .select_related("evaluator", "template")
        .order_by("-created_at")
    )
