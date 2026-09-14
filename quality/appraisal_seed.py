"""
quality/appraisal_seed.py
━━━━━━━━━━━━━━━━━━━━━━━━━
بذرُ قوالب التقييم من الاستمارات الوزاريّة: خطّةٌ تُقرأ أوّلاً، ثمّ كتابةٌ بها.

يكتب في `RoleEvaluationTemplate` و`EvaluationAxis` — وهما ما يقرؤه
`quality.evaluation_views._get_axes_for_employee` بمفتاح `Role.name` للموظّف.
فالقالبُ قالبٌ لكلّ **دور** لا لكلّ استمارة: استمارةُ الوظائف الإداريّة 2 مثلاً
تُبذر أربعَ مرّات (سكرتير، محاسب، استقبال، فنّيّ تقنية).

الخطّةُ لا تكتب شيئاً، والتطبيقُ لا يلمس ما طابق (فالتشغيلُ الثاني صفرُ كتابات)،
ولا يغيّر قالباً عليه تقييماتٌ محفوظة — درجاتُها مخزّنةٌ بمفاتيح محاوره. ويُعاد فحصُ
هذا القفل داخل معاملة الكتابة، فتقييمٌ رُبط بالقالب بين العرض والتطبيق يُقفله.

والتقييماتُ القائمةُ خارج القالب (على المحاور الافتراضيّة، أو على قالب دورٍ سابقٍ
للموظّف) تُعدّ في الخطّة لكلّ دور ولا تُنقل: شاشةُ التقييم تعرض ما عليه درجاتٌ على
محاوره التي حُفظ بها (`evaluation_views._axes_for_evaluation`).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from django.db import transaction
from django.db.models import Count, Q

from core.models import Membership, Role, School

from .appraisal_forms import AppraisalForm, forms_by_role
from .models import EmployeeEvaluation, EvaluationAxis, RoleEvaluationTemplate

_KNOWN_ROLE_NAMES = frozenset(name for name, _label in Role.ROLES)


@dataclass
class TemplatePlan:
    role_name: str
    form: AppraisalForm
    template: RoleEvaluationTemplate | None
    changes: list[str] = field(default_factory=list)
    evaluations: int = 0
    #: تقييماتٌ محفوظةٌ لموظّفين بهذا الدور في العام، ليست على هذا القالب — لا تُنقل إليه.
    outside_template: int = 0

    @property
    def status(self) -> str:
        if self.template is None:
            return "new"
        if not self.changes:
            return "same"
        return "locked" if self.evaluations else "changed"


@dataclass
class SchoolPlan:
    school: School
    year: str
    templates: list[TemplatePlan]
    #: قوالبُ لدورٍ لا وجودَ له في `Role.ROLES` — لا تقرؤها شاشةٌ أبداً.
    orphans: Sequence[RoleEvaluationTemplate]


def _diff(template: RoleEvaluationTemplate, form: AppraisalForm) -> list[str]:
    changes: list[str] = []
    if not template.is_active:
        changes.append("القالب معطَّل ← يُفعَّل")
    current = {a.key: a for a in template.axes.all()}
    for order, axis in enumerate(form.axes, start=1):
        existing = current.pop(axis.key, None)
        if existing is None:
            changes.append(f"+ {axis.key}: {axis.label} ({axis.weight})")
            continue
        if existing.weight != axis.weight:
            changes.append(f"~ {axis.key}: الوزن {existing.weight} ← {axis.weight}")
        if existing.label != axis.label:
            changes.append(f"~ {axis.key}: الاسم «{existing.label}» ← «{axis.label}»")
        if existing.order != order:
            changes.append(f"~ {axis.key}: الترتيب {existing.order} ← {order}")
    changes.extend(
        f"- {key}: {a.label} ({a.weight}) ليس في الاستمارة" for key, a in current.items()
    )
    return changes


def _saved_outside_template(
    school: School, year: str, templates: dict[str, RoleEvaluationTemplate]
) -> dict[str, int]:
    """الدورُ ← عددُ التقييمات المحفوظة لأصحابه في العام وليست على قالبه القائم."""
    roles = dict(
        Membership.objects.filter(school=school, is_active=True).values_list(
            "user_id", "role__name"
        )
    )
    saved = (
        EmployeeEvaluation.objects.filter(school=school, academic_year=year)
        .filter(~Q(status="draft") | Q(total_score__gt=0) | Q(scores__isnull=False))
        .values_list("pk", "employee_id", "template_id")
        .distinct()
    )
    counts: dict[str, int] = {}
    for _pk, employee_id, template_id in saved:
        role_name = roles.get(employee_id)
        if role_name is None:
            continue
        current = templates.get(role_name)
        if current is None or template_id != current.pk:
            counts[role_name] = counts.get(role_name, 0) + 1
    return counts


def build_plan(school: School, year: str) -> SchoolPlan:
    existing = {
        t.role_name: t
        for t in RoleEvaluationTemplate.objects.filter(school=school, academic_year=year)
        .annotate(n_evaluations=Count("evaluations"))
        .prefetch_related("axes")
    }
    outside = _saved_outside_template(school, year, existing)
    plans = []
    for role_name, form in sorted(forms_by_role().items(), key=lambda kv: (kv[1].section, kv[0])):
        template = existing.pop(role_name, None)
        plan = TemplatePlan(
            role_name=role_name,
            form=form,
            template=template,
            outside_template=outside.get(role_name, 0),
        )
        if template is not None:
            plan.changes = _diff(template, form)
            plan.evaluations = template.n_evaluations
        plans.append(plan)
    orphans = [t for name, t in sorted(existing.items()) if name not in _KNOWN_ROLE_NAMES]
    return SchoolPlan(school=school, year=year, templates=plans, orphans=orphans)


@transaction.atomic
def apply_plan(plan: SchoolPlan, *, prune_orphans: bool = False) -> dict[str, int]:
    """يكتب ما في الخطّة. يُرجع عدّاداتٍ للعرض."""
    counts = {"created": 0, "updated": 0, "same": 0, "locked": 0, "pruned": 0}
    for tp in plan.templates:
        if tp.status == "changed" and tp.template is not None:
            # الخطّةُ بُنيت خارج هذه المعاملة: قد يكون تقييمٌ رُبط بالقالب منذئذ.
            locked = (
                RoleEvaluationTemplate.objects.select_for_update().filter(pk=tp.template.pk).first()
            )
            if locked is not None and locked.evaluations.exists():
                tp.evaluations = locked.evaluations.count()
        if tp.status in ("same", "locked"):
            counts[tp.status] += 1
            continue
        template, _ = RoleEvaluationTemplate.objects.update_or_create(
            school=plan.school,
            role_name=tp.role_name,
            academic_year=plan.year,
            defaults={"is_active": True},
        )
        keys = []
        for order, axis in enumerate(tp.form.axes, start=1):
            EvaluationAxis.objects.update_or_create(
                template=template,
                key=axis.key,
                defaults={"label": axis.label, "weight": axis.weight, "order": order},
            )
            keys.append(axis.key)
        EvaluationAxis.objects.filter(template=template).exclude(key__in=keys).delete()
        counts["created" if tp.status == "new" else "updated"] += 1
    if prune_orphans:
        for orphan in plan.orphans:
            if orphan.n_evaluations:  # type: ignore[attr-defined]
                continue
            orphan.delete()
            counts["pruned"] += 1
    return counts
