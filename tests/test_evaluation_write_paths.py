"""[LEGAL] كلُّ مسارٍ يكتب تقييمَ الأداء يحفظ درجاتِه ويمرّ بقيوده — والاعتمادُ للمدير وحده.

المرجع: المادة 16 من النظام الوظيفي لموظفي المدارس (قرار مجلس الوزراء 32/2019)،
«02- النظام الوظيفي لموظفي المدارس.pdf» صفحة الملفّ 10، ونقلُها في
`02_staff_affairs.md:199-200`: «يضع الرئيس المباشر تقييم أداء الموظف ويعتمده مدير
المدرسة»، و«تتولى لجنة شؤون المدارس تقييم أداء مديري المدارس سنوياً».

عيوبُ مراجعة 2026-09-15 التي تحرسها هذه الاختبارات:
  - لوحةُ الإدارة كانت تكتب التقييمَ دون `save_evaluation` فتتجاوز القيد، وحفظُها يعيد
    حسابَ مجموع تقييمات القالب الوزاريّ من المحاور الافتراضيّة الصفريّة فيصفّرها؛
  - `EvaluationScore.total_score` كان يبقى قديماً عند إعادة الحفظ، فيفسد المجموعُ المرجَّح؛
  - الطلبُ المرفوض كان يترك مسودّةً، والعامُ من الرابط بلا تحقّق؛
  - لا مسارَ يكتب «مُعتمد» إلّا لوحة الإدارة.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.contrib import admin as django_admin
from django.core.management import call_command
from django.test import RequestFactory
from django.urls import reverse

from quality.appraisal_forms import forms_by_role
from quality.evaluation_services import (
    AppraisalYearFacts,
    EvaluationRejectedError,
    approve_evaluation,
    save_evaluation,
)
from quality.models import EmployeeEvaluation, EvaluationScore
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

YEAR = "2026-2027"


def _seed(school):
    call_command(
        "seed_quality_templates",
        "--apply",
        "--school",
        school.code,
        "--year",
        YEAR,
        stdout=StringIO(),
    )
    return forms_by_role()["teacher"]


def _url(employee, period="S2", year=YEAR):
    return (
        reverse("create_evaluation", kwargs={"employee_id": employee.pk})
        + f"?year={year}&period={period}"
    )


def _post(form, scores_by_axis, action="submitted"):
    return {**{a.key: str(scores_by_axis(a)) for a in form.axes}, "action": action}


def _full(axis):
    return axis.weight


def _vice_academic(school):
    user = UserFactory(full_name="النائب الأكاديمي")
    MembershipFactory(
        user=user, school=school, role=RoleFactory(school=school, name="vice_academic")
    )
    return user


def _superuser():
    """صاحبُ صلاحيّة التعديل في الإدارة — وإلّا عرضت اللوحةُ كلَّ الحقول للقراءة فلا يُختبر شيء."""
    return UserFactory(full_name="مشرف المنصّة", is_staff=True, is_superuser=True)


def _ministry_evaluation_95(client, school, principal_user, teacher_user):
    form = _seed(school)
    client.force_login(principal_user)
    first = form.axes[0]
    data = _post(form, lambda a: a.weight - 5 if a.key == first.key else a.weight)
    assert client.post(_url(teacher_user), data).status_code == 302
    evaluation = EmployeeEvaluation.objects.get(school=school, employee=teacher_user)
    assert (evaluation.total_score, evaluation.rating) == (95, "excellent")
    return form, evaluation


# ── لوحة الإدارة ─────────────────────────────────────────────────────


@pytest.mark.django_db
def test_admin_cannot_write_scores_rating_or_status(principal_user):
    model_admin = django_admin.site._registry[EmployeeEvaluation]
    request = RequestFactory().get("/admin/")
    request.user = _superuser()
    fields = set(model_admin.get_form(request, EmployeeEvaluation())().fields)
    assert "strengths" in fields  # لم تُحجب اللوحةُ كلُّها
    assert fields.isdisjoint(
        {"status", "rating", "total_score", *EmployeeEvaluation._AXIS_FIELDS, "template"}
    )
    assert model_admin.has_add_permission(request) is False


@pytest.mark.django_db
def test_admin_save_keeps_a_ministry_template_evaluation(
    client, school, principal_user, teacher_user
):
    """كان حفظُه من الإدارة يعيد الحسابَ من المحاور الافتراضيّة: 95 ممتاز ← 0."""
    _form, evaluation = _ministry_evaluation_95(client, school, principal_user, teacher_user)
    model_admin = django_admin.site._registry[EmployeeEvaluation]
    request = RequestFactory().post("/admin/")
    request.user = _superuser()
    form_class = model_admin.get_form(request, evaluation, change=True)
    form = form_class(
        data={"strengths": "ملاحظةٌ من الإدارة", "improvements": "", "goals_next": ""},
        instance=evaluation,
    )
    assert form.is_valid(), form.errors
    model_admin.save_model(request, form.save(commit=False), form, change=True)

    evaluation.refresh_from_db()
    assert (evaluation.total_score, evaluation.rating, evaluation.status, evaluation.strengths) == (
        95,
        "excellent",
        "submitted",
        "ملاحظةٌ من الإدارة",
    )


@pytest.mark.django_db
def test_full_model_save_recomputes_template_evaluation_from_its_scores(
    client, school, principal_user, teacher_user
):
    _form, evaluation = _ministry_evaluation_95(client, school, principal_user, teacher_user)
    evaluation.save()  # بلا update_fields — كما يحفظ أيُّ مسارٍ عامّ
    evaluation.refresh_from_db()
    assert (evaluation.total_score, evaluation.rating) == (95, "excellent")


# ── EvaluationScore ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_resaving_and_a_second_evaluator_use_fresh_totals(
    client, school, principal_user, teacher_user
):
    form = _seed(school)
    client.force_login(principal_user)
    half = _post(form, lambda a: a.weight * 7 // 10)
    client.post(_url(teacher_user), {**half, "action": "draft"})
    score = EvaluationScore.objects.get(evaluator=principal_user)
    first_total = score.total_score
    assert first_total == sum(a.weight * 7 // 10 for a in form.axes)

    client.post(_url(teacher_user), _post(form, _full, action="draft"))
    score.refresh_from_db()
    assert score.total_score == 100  # كان يبقى على المجموع الأوّل

    vice = _vice_academic(school)
    client.force_login(vice)
    client.post(_url(teacher_user), _post(form, _full, action="draft"))
    evaluation = EmployeeEvaluation.objects.get(school=school, employee=teacher_user)
    assert EvaluationScore.objects.get(evaluator=vice).total_score == 100
    # (100×100 + 100×100) / 200 — لا (المجموع القديم×100 + 100×100) / 200.
    assert (evaluation.total_score, evaluation.rating) == (100, "excellent")


# ── العرض: الإنشاء والعام والمدير ─────────────────────────────────────


@pytest.mark.django_db
def test_get_writes_nothing_and_rejected_post_leaves_no_draft(
    monkeypatch, client, school, principal_user, teacher_user
):
    from quality import evaluation_services

    form = _seed(school)
    client.force_login(principal_user)
    assert client.get(_url(teacher_user)).status_code == 200
    assert not EmployeeEvaluation.objects.exists()

    monkeypatch.setattr(
        evaluation_services,
        "year_facts",
        lambda staff, year: AppraisalYearFacts(harsher_sanction=True),
    )
    response = client.post(_url(teacher_user), _post(form, _full))
    assert response.status_code == 302
    assert not EmployeeEvaluation.objects.exists()
    assert not EvaluationScore.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize(("year", "period"), [("2026/2027", "S2"), ("2026-27", "S2"), (YEAR, "S3")])
def test_malformed_year_or_period_is_refused(
    client, school, principal_user, teacher_user, year, period
):
    client.force_login(principal_user)
    assert client.get(_url(teacher_user, period=period, year=year)).status_code == 400
    assert not EmployeeEvaluation.objects.exists()


@pytest.mark.django_db
def test_principal_is_not_evaluated_by_the_school(client, school, principal_user):
    """«وتتولى لجنة شؤون المدارس تقييم أداء مديري المدارس سنوياً» — 02_staff_affairs.md:199."""
    vice = _vice_academic(school)
    client.force_login(vice)
    assert client.get(_url(principal_user)).status_code == 403
    assert client.post(_url(principal_user), {"action": "draft"}).status_code == 403
    assert not EmployeeEvaluation.objects.exists()


# ── الاعتماد ─────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_principal_approves_a_submitted_report_from_the_screen(
    client, school, principal_user, teacher_user
):
    _form, evaluation = _ministry_evaluation_95(client, school, principal_user, teacher_user)
    page = client.get(_url(teacher_user))
    assert page.context["can_approve"] is True

    response = client.post(reverse("approve_evaluation", kwargs={"eval_id": evaluation.pk}))
    assert response.status_code == 302
    evaluation.refresh_from_db()
    assert (evaluation.status, evaluation.total_score) == ("approved", 95)

    # بعد الاعتماد لا تُعدَّل الدرجات، ويستطيع الموظّف الإقرار.
    with pytest.raises(EvaluationRejectedError, match="معتمَد"):
        save_evaluation(
            evaluation=evaluation, evaluator=principal_user, axes=[], data={"action": "draft"}
        )


@pytest.mark.django_db
def test_only_the_principal_approves_and_only_a_submitted_report(
    client, school, principal_user, teacher_user
):
    form, evaluation = _ministry_evaluation_95(client, school, principal_user, teacher_user)
    vice = _vice_academic(school)
    client.force_login(vice)
    assert client.get(_url(teacher_user)).context["can_approve"] is False
    client.post(reverse("approve_evaluation", kwargs={"eval_id": evaluation.pk}))
    evaluation.refresh_from_db()
    assert evaluation.status == "submitted"

    client.force_login(principal_user)
    client.post(_url(teacher_user), _post(form, _full, action="draft"))
    with pytest.raises(EvaluationRejectedError, match="مُقدَّم"):
        approve_evaluation(evaluation=evaluation, approver=principal_user)


@pytest.mark.django_db
def test_approval_rechecks_the_article_restrictions(
    monkeypatch, client, school, principal_user, teacher_user
):
    from quality import evaluation_services

    _form, evaluation = _ministry_evaluation_95(client, school, principal_user, teacher_user)
    monkeypatch.setattr(
        evaluation_services,
        "year_facts",
        lambda staff, year: AppraisalYearFacts(unexcused_absence_days=6),
    )
    with pytest.raises(EvaluationRejectedError, match="المادة 17"):
        approve_evaluation(evaluation=evaluation, approver=principal_user)
    evaluation.refresh_from_db()
    assert evaluation.status == "submitted"
