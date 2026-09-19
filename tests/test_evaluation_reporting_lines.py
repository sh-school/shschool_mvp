"""[LEGAL] «يضع الرئيس المباشر تقييم أداء الموظف» — المادة 16، وخطُّ التبعيّة من بطاقات الوصف.

المصدر: «02- النظام الوظيفي لموظفي المدارس.pdf» المادة 16 (`02_staff_affairs.md:200`)، وخانةُ
«المسؤول المباشر» في `05- الوصف الوظيفي/*.pdf` — قُرئت بطاقاتُ الأدوار الثلاثة والعشرين من الصورة:
المعلّمُ ← نائب المدير للشؤون الأكاديمية، والنائبان والسكرتيرُ ← مدير المدرسة (فلا يتبع أحدُ
النائبين الآخر)، وبطاقتا النائبين: «متابعة وتقييم أداء من يندرج تحت مسؤولياته».
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from core.models import Role
from quality.evaluation_selectors import get_evaluable_staff
from quality.evaluation_services import EvaluationRejectedError, save_evaluation
from quality.models import EmployeeEvaluation
from quality.reporting_lines import DIRECT_SUPERVISOR, may_place, rejection_reason
from tests.test_evaluation_review_round1 import YEAR, _post_total, _seed, _staff, _url


def test_every_mapped_role_exists_in_the_role_registry():
    known = {name for name, _label in Role.ROLES}
    assert set(DIRECT_SUPERVISOR) <= known
    assert set(DIRECT_SUPERVISOR.values()) <= known


@pytest.mark.parametrize(
    ("evaluator", "employee", "allowed"),
    [
        ({"vice_academic"}, "teacher", True),
        ({"vice_academic"}, "lab_technician", True),
        ({"vice_admin"}, "social_worker", True),
        ({"vice_admin"}, "teacher", False),
        ({"vice_academic"}, "nurse", False),
        # لا يتبع أحدُ النائبين الآخر، ولا يضع أيٌّ منهما تقريرَ السكرتير.
        ({"vice_academic"}, "vice_admin", False),
        ({"vice_admin"}, "vice_academic", False),
        ({"vice_admin"}, "secretary", False),
        # المديرُ معتمِدُ كلّ تقرير ورأسُ الهرم، وهو المسؤول المباشر للنائبين والسكرتير.
        ({"principal"}, "vice_admin", True),
        ({"principal"}, "secretary", True),
        ({"principal"}, "teacher", True),
        # من لا بطاقةَ له في المصدر: قرارُ المالك 2026-09-19 — يتبعون النائبَ الإداريّ.
        ({"vice_admin"}, "accountant", True),
        ({"vice_academic"}, "accountant", False),
        ({"vice_admin"}, "academic_advisor", True),
        ({"vice_academic"}, "teacher_assistant", False),
        ({"principal"}, "accountant", True),
    ],
)
def test_only_the_direct_supervisor_or_the_principal_places(evaluator, employee, allowed):
    assert may_place(evaluator, employee) is allowed


def test_the_rejection_names_the_direct_supervisor():
    assert "نائب المدير للشؤون الأكاديمية" in rejection_reason("teacher")
    assert "مدير المدرسة" in rejection_reason("vice_admin")


@pytest.mark.django_db
def test_the_other_wings_vice_cannot_open_or_save_a_report(client, school, teacher_user):
    form = _seed(school)
    wrong = _staff(school, "vice_admin", "النائب الإداري")
    right = _staff(school, "vice_academic", "النائب الأكاديمي")

    client.force_login(wrong)
    assert client.get(_url(teacher_user)).status_code == 403
    assert client.post(_url(teacher_user), _post_total(form, 90)).status_code == 403
    assert not EmployeeEvaluation.objects.filter(employee=teacher_user).exists()

    client.force_login(right)
    assert client.get(_url(teacher_user)).status_code == 200


@pytest.mark.django_db
def test_the_service_rejects_it_too(school, teacher_user):
    form = _seed(school)
    wrong = _staff(school, "vice_admin", "النائب الإداري")
    evaluation = EmployeeEvaluation.objects.create(
        school=school, employee=teacher_user, evaluator=wrong, academic_year=YEAR, period="S2"
    )
    axes = [(a.key, a.label, a.weight) for a in form.axes]

    with pytest.raises(EvaluationRejectedError, match="الرئيس المباشر"):
        save_evaluation(
            evaluation=evaluation, evaluator=wrong, axes=axes, data=_post_total(form, 90)
        )


@pytest.mark.django_db
def test_the_dashboard_hides_the_button_from_a_non_supervisor(school, teacher_user):
    wrong = _staff(school, "vice_admin", "النائب الإداري")
    nurse = _staff(school, "nurse", "الممرّض")

    rows = {r["user"].pk: r for r in get_evaluable_staff(school, YEAR, viewer=wrong)}

    assert rows[teacher_user.pk]["can_place"] is False
    assert rows[nurse.pk]["can_place"] is True
    assert reverse("evaluation_dashboard")
