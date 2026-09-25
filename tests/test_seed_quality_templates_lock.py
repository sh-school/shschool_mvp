"""
اختبارُ أمر البذر seed_quality_templates: لا يُعدَّل وزنُ/تسميةُ محورٍ عليه
تقييمٌ معتمَدٌ (`FINAL_STATUSES`) — إصلاح ب.2، فذلك يُفسد مجموعاً معتمَداً بالفعل.

والمسودّةُ (ولو عليها درجاتٌ محفوظة) ليست مقفلة: يُصحَّح القالبُ وتُعاد مسودّةً بلا
مجموعٍ ولا مستوى (`appraisal_seed._reopen_on_changed_template`، ADR-0002 §5).
"""

import pytest
from django.core.management import call_command

from core.academic_calendar import default_academic_year
from quality.appraisal_forms import forms_by_role
from quality.models import EvaluationAxis, EvaluationScore, RoleEvaluationTemplate
from tests.test_quality_models import make_admin, make_evaluation, make_teacher


@pytest.mark.django_db
def test_seed_command_does_not_overwrite_axis_of_locked_template(school):
    admin = make_admin(school)
    teacher = make_teacher(school)
    template = RoleEvaluationTemplate.objects.create(
        school=school, role_name="teacher", academic_year=default_academic_year()
    )
    axis = EvaluationAxis.objects.create(
        template=template, key="planning_development", label="عنوانٌ قديم", weight=99, order=1
    )
    ev = make_evaluation(
        school,
        teacher,
        admin,
        template=template,
        academic_year=template.academic_year,
        status="approved",
    )
    EvaluationScore.objects.create(evaluation=ev, evaluator=admin, weight=100, axis_professional=25)

    call_command("seed_quality_templates", "--apply")

    axis.refresh_from_db()
    assert axis.weight == 99, "عُدِّل وزنُ محورٍ عليه تقييمٌ معتمَد"
    assert axis.label == "عنوانٌ قديم"


@pytest.mark.django_db
def test_seed_command_rewrites_axes_under_a_draft_and_reopens_it(school):
    admin = make_admin(school)
    teacher = make_teacher(school)
    template = RoleEvaluationTemplate.objects.create(
        school=school, role_name="teacher", academic_year=default_academic_year()
    )
    EvaluationAxis.objects.create(
        template=template, key="planning_development", label="عنوانٌ قديم", weight=99, order=1
    )
    ev = make_evaluation(
        school, teacher, admin, template=template, academic_year=template.academic_year
    )
    EvaluationScore.objects.create(evaluation=ev, evaluator=admin, weight=100, axis_professional=25)

    call_command("seed_quality_templates", "--apply")

    template.refresh_from_db()
    assert sum(template.axes.values_list("weight", flat=True)) == 100
    assert not template.axes.filter(label="عنوانٌ قديم").exists()


@pytest.mark.django_db
def test_seed_command_creates_a_template_per_role_from_the_seven_forms(school):
    call_command("seed_quality_templates", "--apply")

    templates = RoleEvaluationTemplate.objects.filter(
        school=school, academic_year=default_academic_year()
    )
    assert set(templates.values_list("role_name", flat=True)) == set(forms_by_role())
    assert len({form.title for form in forms_by_role().values()}) == 7
    for template in templates:
        total_weight = sum(template.axes.values_list("weight", flat=True))
        assert total_weight == 100, f"{template.role_name}: مجموع الأوزان {total_weight} لا 100"
