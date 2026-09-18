"""
اختبارُ أمر البذر seed_quality_templates: لا يُعدَّل وزنُ/تسميةُ محورٍ عليه
تقييمٌ مُقفَل (مُقدَّمٌ أو معتمَدٌ أو له درجاتٌ محفوظة عبر EvaluationScore) —
إصلاح ب.2، فذلك يُفسد مجموعاً مُعتمَداً أو مُقدَّماً بالفعل.
"""

import pytest
from django.core.management import call_command

from core.academic_calendar import default_academic_year
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
        school, teacher, admin, template=template, academic_year=template.academic_year
    )
    EvaluationScore.objects.create(evaluation=ev, evaluator=admin, weight=100, axis_professional=25)

    call_command("seed_quality_templates", "--apply")

    axis.refresh_from_db()
    assert axis.weight == 99, "عُدِّل وزنُ محورٍ عليه تقييمٌ مقفلٌ (له درجاتٌ محفوظة)"
    assert axis.label == "عنوانٌ قديم"


@pytest.mark.django_db
def test_seed_command_creates_the_seven_ministry_templates(school):
    call_command("seed_quality_templates", "--apply")

    created = set(
        RoleEvaluationTemplate.objects.filter(
            school=school, academic_year=default_academic_year()
        ).values_list("role_name", flat=True)
    )
    assert created == {
        "teacher",
        "admin_vice_principal",
        "academic_vice_principal",
        "worker",
        "admin_role_1",
        "admin_role_2",
        "admin_role_3",
    }
    for template in RoleEvaluationTemplate.objects.filter(
        school=school, academic_year=default_academic_year()
    ):
        total_weight = sum(template.axes.values_list("weight", flat=True))
        assert total_weight == 100, f"{template.role_name}: مجموع الأوزان {total_weight} لا 100"
