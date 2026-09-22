"""[LEGAL] عيوبُ المراجعة المستقلّة لفرع تقييم الأداء قبل الدفع — جولة 7 (2026-09-19).

كلُّ اختبارٍ هنا سقط على الفرع قبل إصلاحه:

  - أدوارٌ تسمّيها الاستماراتُ الوزاريّةُ وتُبذر قوالبُها لم تكن في بوّابة الوحدة: تُقيَّم ولا ترى
    تقريرَها ولا تُقرّ به، فلا تبدأ مهلةُ التظلّم (المادة 20، صفحتا الملفّ 12–13).
  - بذرٌ يصحّح اسمَ محورٍ (بلا تغيير وزنٍ ولا مفتاح) كان يُرجع كلَّ تقريرٍ غيرِ معتمَدٍ إلى
    مسودّةٍ بمجموعٍ صفر — ولا يمسّ الاسمُ مجموعاً.
  - ردُّ 409 نصٌّ فيه اسمُ الموظّف يُخدَم HTML.
  - صاحبُ عضويّتين يظهر صفّين في اللوحة.
  - حذفٌ جماعيٌّ لقوالب من لوحة الإدارة يسقط بـRestrictedError.
"""

from __future__ import annotations

import pytest
from django.contrib import admin as django_admin
from django.test import RequestFactory

from core.module_registry import get_module
from quality.evaluation_selectors import get_evaluable_staff
from quality.models import (
    _EVALUABLE_ROLES,
    EmployeeEvaluation,
    EvaluationAxis,
    EvaluationScore,
    RoleEvaluationTemplate,
)
from tests.conftest import MembershipFactory, RoleFactory, UserFactory
from tests.test_evaluation_review_round1 import YEAR, _form_scores, _seed, _staff, _url
from tests.test_evaluation_review_round6 import _seed_output, _teacher_template


def test_every_evaluable_role_passes_the_module_gate():
    gate = get_module("quality_evaluations")
    assert gate is not None
    missing = sorted(_EVALUABLE_ROLES - set(gate.allowed_roles))
    assert not missing, f"أدوارٌ تُقيَّم ولا يفتح أصحابُها تقريرَهم: {missing}"


@pytest.mark.django_db
def test_a_label_only_correction_does_not_reset_a_submitted_report(school, teacher_user):
    form = _seed(school)
    vice = _staff(school, "vice_academic")
    evaluation = EmployeeEvaluation.objects.create(
        school=school, employee=teacher_user, evaluator=vice, academic_year=YEAR,
        period="S2", template=_teacher_template(school), status="submitted",
    )  # fmt: skip
    EvaluationScore.objects.create(
        evaluation=evaluation, evaluator=vice, custom_axes=_form_scores(form, 90)
    )
    evaluation.save()
    evaluation.refresh_from_db()
    assert (evaluation.status, evaluation.total_score) == ("submitted", 90)

    first = _teacher_template(school).axes.order_by("order").first()
    EvaluationAxis.objects.filter(pk=first.pk).update(label="اسمٌ قديم")
    assert "reopened': 0" in _seed_output(school)

    evaluation.refresh_from_db()
    assert (evaluation.status, evaluation.total_score) == ("submitted", 90)
    first.refresh_from_db()
    assert first.label != "اسمٌ قديم"


@pytest.mark.django_db
def test_a_weight_change_still_reopens_the_report(school, teacher_user):
    form = _seed(school)
    vice = _staff(school, "vice_academic")
    evaluation = EmployeeEvaluation.objects.create(
        school=school, employee=teacher_user, evaluator=vice, academic_year=YEAR,
        period="S2", template=_teacher_template(school), status="submitted",
    )  # fmt: skip
    EvaluationScore.objects.create(
        evaluation=evaluation, evaluator=vice, custom_axes=_form_scores(form, 90)
    )
    first = _teacher_template(school).axes.order_by("order").first()
    EvaluationAxis.objects.filter(pk=first.pk).update(weight=first.weight + 5)

    _seed_output(school)

    evaluation.refresh_from_db()
    assert (evaluation.status, evaluation.total_score) == ("draft", 0)


@pytest.mark.django_db
def test_the_409_for_an_unseeded_role_is_not_served_as_html(client, school, principal_user):
    employee = _staff(school, "teacher", name="<b>x</b>")
    RoleEvaluationTemplate.objects.filter(school=school).delete()
    vice = _staff(school, "vice_academic")
    client.force_login(vice)

    response = client.get(_url(employee))

    assert response.status_code == 409
    assert response["Content-Type"].startswith("text/plain")


@pytest.mark.django_db
def test_an_employee_with_two_evaluable_roles_is_listed_once(school):
    user = UserFactory(full_name="موظّفٌ بعضويّتين")
    for name in ("teacher", "librarian"):
        MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=name))

    rows = [r for r in get_evaluable_staff(school, YEAR) if r["user"].pk == user.pk]

    assert len(rows) == 1


@pytest.mark.django_db
def test_no_bulk_delete_of_templates_in_the_admin(school, principal_user):
    request = RequestFactory().get("/")
    request.user = UserFactory(is_superuser=True, is_staff=True)
    model_admin = django_admin.site._registry[RoleEvaluationTemplate]

    assert model_admin.has_delete_permission(request, None) is False
