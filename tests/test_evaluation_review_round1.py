"""[LEGAL] عيوبُ المراجعة العدائيّة لموجة تقييم الأداء (جولة الإصلاح 1، 2026-09-15).

كلُّ اختبارٍ هنا سقط على الفرع قبل إصلاحه. والمراجع:

  - «02- النظام الوظيفي لموظفي المدارس.pdf» (قرار مجلس الوزراء 32/2019، ممسوحٌ؛ قُرئ من
    الصورة): المادتان 15 و16 صفحة الملفّ 10 (المطبوعة 24)، والمادة 20 صفحتا الملفّ 12–13
    (المطبوعتان 26–27)، ونقلُهما في `02_staff_affairs.md:199-211`.
  - «استمارة تقييم المعلم والدليل التفسيري.pdf» ص2: «تاريخ استلام الموظف (يرجى تدوين
    التاريخ في حالة رفض الموظف التوقيع)».
  - الاستماراتُ السبع في «06- تقييم أداء الموظفين/»: ملاحظةُ التظلّم في طبقة نصّ خمسٍ منها،
    ولا أثرَ لـ«ظلم» في استمارتَي المعلم والنائب الأكاديمي (ولا في صورتَي صفحتَي توقيعهما).
"""

from __future__ import annotations

import importlib
import uuid
from datetime import date, datetime, time
from io import StringIO
from pathlib import Path

import pytest
from django.apps import apps as django_apps
from django.contrib import admin as django_admin
from django.core.management import call_command
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from quality.appraisal_forms import forms_by_role
from quality.evaluation_services import (
    EvaluationRejectedError,
    approve_evaluation,
    save_evaluation,
)
from quality.evaluation_views import _DEFAULT_AXES
from quality.models import (
    EmployeeEvaluation,
    EvaluationAxis,
    EvaluationScore,
    RoleEvaluationTemplate,
)
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

YEAR = "2026-2027"
REFERENCE = Path("AAdocs/ministry_data/2026_2027/06_attendance_performance_review.md")


def _seed(school):
    call_command(
        "seed_quality_templates", "--apply", "--school", school.code, "--year", YEAR,
        stdout=StringIO(),
    )  # fmt: skip
    return forms_by_role()["teacher"]


def _url(employee, period="S2"):
    return (
        reverse("create_evaluation", kwargs={"employee_id": employee.pk})
        + f"?year={YEAR}&period={period}"
    )


def _staff(school, role_name, name=None):
    user = UserFactory(full_name=name or role_name)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role_name))
    return user


def _post_total(form, total, action="submitted"):
    """درجاتُ محاور الاستمارة مجموعُها `total` — تُنقص من المحاور بالترتيب."""
    missing = 100 - total
    data = {}
    for axis in form.axes:
        cut = min(missing, axis.weight)
        data[axis.key] = str(axis.weight - cut)
        missing -= cut
    data["action"] = action
    return data


def _placed_by_vice(client, school, teacher_user, total=92):
    form = _seed(school)
    vice = _staff(school, "vice_academic", "النائب الأكاديمي")
    client.force_login(vice)
    assert client.post(_url(teacher_user), _post_total(form, total)).status_code == 302
    evaluation = EmployeeEvaluation.objects.get(school=school, employee=teacher_user)
    assert (evaluation.total_score, evaluation.status) == (total, "submitted")
    return form, vice, evaluation


# ── 1. المادة 20: «ويكون قرار اللجنة في التظلم نهائياً بعد اعتماده من الوزير» ─────


def _acknowledged(school, employee, evaluator, known_on):
    evaluation = EmployeeEvaluation.objects.create(
        school=school,
        employee=employee,
        evaluator=evaluator,
        academic_year=YEAR,
        period="S2",
        status="acknowledged",
    )
    evaluation.acknowledged_at = timezone.make_aware(datetime.combine(known_on, time(10)))
    return evaluation


@pytest.mark.django_db
def test_committee_decision_is_not_final_before_the_minister_approves_it(
    school, principal_user, teacher_user
):
    """«02- النظام الوظيفي لموظفي المدارس.pdf» صفحة الملفّ 13 (المطبوعة 27)، المادة 20."""
    evaluation = _acknowledged(school, teacher_user, principal_user, date(2027, 6, 20))
    evaluation.grievance_submitted_on = date(2027, 6, 25)
    evaluation.grievance_decided_on = date(2027, 7, 1)
    assert evaluation.is_final(today=date(2027, 7, 2)) is False
    # والقرارُ الصادرُ لا تُسقطه مهلةُ الثلاثين: «بمثابة قرار بالرفض» لمضيّها «دون إخطار».
    assert evaluation.is_final(today=date(2027, 9, 1)) is False
    evaluation.grievance_decision_approved_on = date(2027, 7, 10)
    assert evaluation.is_final(today=date(2027, 7, 10)) is True


# ── 2. رفضُ التوقيع: «يرجى تدوين التاريخ في حالة رفض الموظف التوقيع» ────────────


@pytest.mark.django_db
def test_receipt_date_recorded_on_refusal_starts_the_grievance_window(
    client, school, principal_user, teacher_user
):
    """استمارة المعلم ص2؛ والمادة 20 تبدأ المهلة «من تاريخ علمه» لا من إقراره."""
    evaluation = EmployeeEvaluation.objects.create(
        school=school,
        employee=teacher_user,
        evaluator=principal_user,
        academic_year=YEAR,
        period="S2",
        status="approved",
    )
    # لحظةُ اعتماد المدير: تاريخُ الاستلام لا يسبقها (المادة 20، جولة الإصلاح 2).
    EmployeeEvaluation.objects.filter(pk=evaluation.pk).update(
        approved_at=timezone.make_aware(datetime.combine(date(2026, 6, 18), time(9)))
    )
    client.force_login(principal_user)
    response = client.post(
        reverse("record_evaluation_receipt", kwargs={"eval_id": evaluation.pk}),
        {"received_on": "2026-06-20"},
    )
    assert response.status_code == 302
    evaluation.refresh_from_db()
    assert (evaluation.received_on, evaluation.status) == (date(2026, 6, 20), "approved")
    assert evaluation.grievance_deadline() == date(2026, 7, 5)
    assert evaluation.is_final(today=date(2026, 7, 5)) is False
    assert evaluation.is_final(today=date(2026, 7, 6)) is True


@pytest.mark.django_db
def test_only_the_principal_records_the_receipt_and_not_in_the_future(
    client, school, principal_user, teacher_user
):
    evaluation = EmployeeEvaluation.objects.create(
        school=school,
        employee=teacher_user,
        evaluator=principal_user,
        academic_year=YEAR,
        period="S2",
        status="approved",
    )
    url = reverse("record_evaluation_receipt", kwargs={"eval_id": evaluation.pk})
    client.force_login(_staff(school, "vice_academic"))
    client.post(url, {"received_on": "2026-06-20"})
    client.force_login(principal_user)
    client.post(url, {"received_on": "2099-06-20"})
    evaluation.refresh_from_db()
    assert evaluation.received_on is None


# ── 3. الأدوارُ الصامتة لا تُولَّد لها استمارةٌ سنويّةٌ على محاور مخترعة ─────────


@pytest.mark.django_db
# bus_supervisor خرج منها: تكليفٌ على «ملاحظ طلبة» (جولة الإصلاح 3، test_evaluation_review_round3).
@pytest.mark.parametrize("role_name", ["nurse", "coordinator", "ese_teacher", "admin"])
def test_silent_roles_get_no_annual_report_on_invented_axes(
    client, school, principal_user, role_name
):
    """ADR-0002 §6.4 و§6.6 بند 12: لا خانةَ لها في رأس أيٍّ من الاستمارات السبع."""
    _seed(school)
    employee = _staff(school, role_name)
    client.force_login(principal_user)
    assert client.get(_url(employee)).status_code == 409
    data = {field: "25" for field, _l, _m in _DEFAULT_AXES} | {"action": "submitted"}
    assert client.post(_url(employee), data).status_code == 409
    assert not EmployeeEvaluation.objects.filter(employee=employee).exists()


@pytest.mark.django_db
def test_annual_report_is_never_saved_or_approved_on_default_axes(
    school, principal_user, teacher_user
):
    evaluation = EmployeeEvaluation.objects.create(
        school=school, employee=teacher_user, evaluator=principal_user,
        academic_year=YEAR, period="S2",
    )  # fmt: skip
    data = {field: "20" for field, _l, _m in _DEFAULT_AXES} | {"action": "submitted"}
    with pytest.raises(EvaluationRejectedError, match="استمارة"):
        save_evaluation(
            evaluation=evaluation, evaluator=principal_user, axes=_DEFAULT_AXES, data=data
        )
    EmployeeEvaluation.objects.filter(pk=evaluation.pk).update(status="submitted")
    evaluation.refresh_from_db()
    vice = _staff(school, "vice_academic")
    EmployeeEvaluation.objects.filter(pk=evaluation.pk).update(evaluator=vice)
    with pytest.raises(EvaluationRejectedError, match="استمارة"):
        approve_evaluation(evaluation=evaluation, approver=principal_user)


# ── 4. المرجع 06: ملاحظةُ التظلّم في خمس استمارات لا في السبع ──────────────────

#: الاستماراتُ التي تحمل طبقةُ نصّها «يتظلم» (PyMuPDF، 2026-09-15): الفئة العمالية ص2،
#: النائب الإداري، والوظائف الإدارية 1 و2 و3. واستمارتا المعلم والنائب الأكاديمي بلا «ظلم».
FORMS_WITHOUT_GRIEVANCE_NOTE = ("المعلم", "النائب الأكاديمي")


def test_reference_does_not_attribute_the_grievance_note_to_all_seven_forms():
    lines = REFERENCE.read_text(encoding="utf-8").split("\n")
    note = next(line for line in lines if "ملاحظة تظلّم" in line)
    assert "كل استمارة" not in note
    assert all(name in note for name in FORMS_WITHOUT_GRIEVANCE_NOTE), note
    summary = next(
        line for line in lines if line.startswith("جميع الاستمارات السبع تشترك في: مقياس")
    )
    clause = next(part for part in summary.split("؛") if "التظلم" in part)
    assert "ونفس نص" not in clause, summary
    assert all(name in clause for name in FORMS_WITHOUT_GRIEVANCE_NOTE), summary


# ── 5. القفل: حفظُ المقيِّم لا يكتب فوق اعتماد المدير ─────────────────────────


@pytest.mark.django_db
def test_stale_evaluator_save_cannot_overwrite_the_principals_approval(
    client, school, principal_user, teacher_user
):
    form, vice, evaluation = _placed_by_vice(client, school, teacher_user)
    stale = EmployeeEvaluation.objects.get(pk=evaluation.pk)  # في يد النائب: «مُقدَّم»
    approve_evaluation(evaluation=evaluation, approver=principal_user)

    axes = [(a.key, a.label, a.weight) for a in form.axes]
    with pytest.raises(EvaluationRejectedError, match="معتمَد"):
        save_evaluation(
            evaluation=stale, evaluator=vice, axes=axes, data=_post_total(form, 40, "draft")
        )
    evaluation.refresh_from_db()
    assert (evaluation.status, evaluation.total_score) == ("approved", 92)


@pytest.mark.django_db
def test_save_locks_the_evaluation_row_before_reading_scores(
    client, school, principal_user, teacher_user
):
    form, vice, evaluation = _placed_by_vice(client, school, teacher_user)
    axes = [(a.key, a.label, a.weight) for a in form.axes]
    with CaptureQueriesContext(connection) as queries:
        save_evaluation(
            evaluation=evaluation, evaluator=vice, axes=axes, data=_post_total(form, 90, "draft")
        )
    sql = [q["sql"] for q in queries.captured_queries]
    locked_at = next((i for i, s in enumerate(sql) if "FOR UPDATE" in s), None)
    scores_read = next(i for i, s in enumerate(sql) if 'FROM "quality_evaluationscore"' in s)
    assert locked_at is not None and locked_at < scores_read


# ── 6. لوحةُ الإدارة لا تفكّ قالباً عليه تقييمات ولا تعدّل محاوره ─────────────


@pytest.mark.django_db
def test_admin_cannot_delete_or_edit_axes_of_a_template_with_evaluations(
    client, school, principal_user, teacher_user
):
    _form, _vice, evaluation = _placed_by_vice(client, school, teacher_user)
    template = evaluation.template
    request = RequestFactory().get("/admin/")
    request.user = UserFactory(is_staff=True, is_superuser=True)
    template_admin = django_admin.site._registry[RoleEvaluationTemplate]
    assert template_admin.has_delete_permission(request, template) is False
    inline = template_admin.get_inline_instances(request, template)[0]
    assert inline.model is EvaluationAxis
    assert inline.has_change_permission(request, template) is False
    assert inline.has_add_permission(request, template) is False
    assert inline.has_delete_permission(request, template) is False

    # وقالبٌ بلا تقييمات يبقى قابلاً للتحرير.
    free = RoleEvaluationTemplate.objects.get(
        school=school, role_name="it_technician", academic_year=YEAR
    )
    assert template_admin.has_delete_permission(request, free) is True

    # والحذفُ من خارج اللوحة لا يفكّ الربطَ صامتاً.
    from django.db.models import RestrictedError

    with pytest.raises(RestrictedError):
        template.delete()
    evaluation.refresh_from_db()
    assert evaluation.template_id == template.pk


# ── 7 و8. المدير لا يُقيَّم من المدرسة، ولا يعتمد تقريرَه بيده ─────────────────


def _principal_with_an_older_teacher_membership(school):
    user = UserFactory(full_name="مديرٌ بعضويّتين")
    MembershipFactory(
        id=uuid.UUID(int=1), user=user, school=school,
        role=RoleFactory(school=school, name="teacher"),
    )  # fmt: skip
    MembershipFactory(
        id=uuid.UUID(int=2**128 - 1), user=user, school=school,
        role=RoleFactory(school=school, name="principal"),
    )  # fmt: skip
    return user


@pytest.mark.django_db
def test_a_principal_with_a_second_membership_is_still_not_evaluated(client, school):
    """المادة 15: «وتتولى لجنة شؤون المدارس، تقييم أداء مديري المدارس سنوياً» (02:199)."""
    principal = _principal_with_an_older_teacher_membership(school)
    _seed(school)
    client.force_login(_staff(school, "vice_academic"))
    assert client.get(_url(principal)).status_code == 403
    assert client.post(_url(principal), {"action": "draft"}).status_code == 403
    assert not EmployeeEvaluation.objects.filter(employee=principal).exists()


@pytest.mark.django_db
def test_principal_cannot_approve_his_own_report(school, principal_user):
    vice = _staff(school, "vice_academic")
    evaluation = EmployeeEvaluation.objects.create(
        school=school, employee=principal_user, evaluator=vice,
        academic_year=YEAR, period="S1", status="submitted",
    )  # fmt: skip
    with pytest.raises(EvaluationRejectedError, match="لجنة شؤون المدارس"):
        approve_evaluation(evaluation=evaluation, approver=principal_user)
    evaluation.refresh_from_db()
    assert evaluation.status == "submitted"


# ── 9 و11 و12. المستوى والرقم المعروض والهجرة 0018 ──────────────────────────


def _migration_0018_forward():
    module = importlib.import_module("quality.migrations.0018_employeeevaluation_five_level_rating")
    return module.Migration.operations[-1].code


def _weighted_evaluation(school, employee, evaluator, totals):
    """تقييمٌ على قالبٍ بمقيِّمين درجاتُهم `totals` (وزنُ كلٍّ 100)."""
    template = RoleEvaluationTemplate.objects.create(
        school=school, role_name="teacher", academic_year=YEAR
    )
    # محورٌ واحدٌ مفتاحُه مفتاحُ الدرجات — وإلّا لم تكن درجاتِ الاستمارة (`has_form_scores`).
    EvaluationAxis.objects.create(template=template, key="all", label="الكلّ", weight=100)
    evaluation = EmployeeEvaluation.objects.create(
        school=school, employee=employee, evaluator=evaluator, template=template,
        academic_year=YEAR, period="S2", status="submitted",
    )  # fmt: skip
    for n, total in enumerate(totals):
        EvaluationScore.objects.create(
            evaluation=evaluation,
            evaluator=evaluator if n == 0 else UserFactory(),
            custom_axes={"all": total},
        )
    return evaluation


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("totals", "shown", "rating"),
    [
        ((90, 89), 89, "very_good"),  # 89.5 — كان يُعرض 90 بجوار «جيد جداً (89–76)»
        ((50, 49), 49, "weak"),  # 49.5 — كان 50 بجوار «ضعيف (أقل من 50)»
        ((76, 75, 75), 76, "very_good"),  # 75.33 — كان 75 بجوار «جيد جداً (89–76)»
        ((66, 65, 65), 66, "good"),  # 65.33 — كان 65 بجوار «جيد (75–66)»
        ((66, 65), 66, "good"),  # 65.5 — التقريبُ نفسُه في النطاق
    ],
)
def test_shown_total_stays_inside_its_levels_printed_range(
    school, principal_user, teacher_user, totals, shown, rating
):
    evaluation = _weighted_evaluation(school, teacher_user, principal_user, totals)
    evaluation.recalculate_from_scores()
    evaluation.refresh_from_db()
    assert (evaluation.total_score, evaluation.rating) == (shown, rating)


@pytest.mark.django_db
def test_migration_0018_classifies_weighted_rows_like_the_model(
    school, principal_user, teacher_user
):
    evaluation = _weighted_evaluation(school, teacher_user, principal_user, (90, 89))
    EmployeeEvaluation.objects.filter(pk=evaluation.pk).update(total_score=90, rating="excellent")
    _migration_0018_forward()(django_apps, None)
    evaluation.refresh_from_db()
    assert (evaluation.total_score, evaluation.rating) == (89, "very_good")


@pytest.mark.django_db
def test_migration_0018_clears_the_rating_of_blank_drafts(school, principal_user, teacher_user):
    blank = EmployeeEvaluation.objects.create(
        school=school, employee=teacher_user, evaluator=principal_user,
        academic_year=YEAR, period="S1",
    )  # fmt: skip
    EmployeeEvaluation.objects.filter(pk=blank.pk).update(rating="needs_dev")
    _migration_0018_forward()(django_apps, None)
    blank.refresh_from_db()
    assert blank.rating == ""


@pytest.mark.django_db
def test_blank_and_internal_rows_are_not_counted_or_shown_as_weak(
    client, school, principal_user, teacher_user
):
    common = {"school": school, "evaluator": principal_user, "academic_year": YEAR}
    EmployeeEvaluation.objects.create(employee=teacher_user, period="S2", **common)  # مسودّةٌ فارغة
    EmployeeEvaluation.objects.create(
        employee=teacher_user, period="S1", status="submitted", axis_professional=10, **common
    )
    other = _staff(school, "it_technician")
    EmployeeEvaluation.objects.create(
        employee=other, period="S2", status="approved", axis_professional=10, **common
    )
    client.force_login(principal_user)
    dist = client.get(reverse("evaluation_dashboard") + f"?year={YEAR}").context["rating_dist"]
    # صفُّ S2 المعتمَدُ على المحاور الأربعة ليس على الاستمارة، فلا مستوى وزاريَّ له ولا يُعدّ
    # (جولة الإصلاح 3، test_annual_rows_off_the_form_get_no_article_16_level).
    assert dist == {}

    client.force_login(teacher_user)
    assert client.get(reverse("my_evaluations")).context["evals"] == []


# ── 10. المديرُ يفتح التقريرَ ليعتمده: يرى درجاتِ واضعه، ولا يصير مقيِّماً ثانياً ──


@pytest.mark.django_db
def test_principal_sees_the_placers_scores_and_cannot_split_the_total(
    client, school, principal_user, teacher_user
):
    """المادة 16: «يضع الرئيس المباشر تقييم أداء الموظف ويعتمد من مدير المدرسة» — واضعٌ واحد."""
    form, vice, evaluation = _placed_by_vice(client, school, teacher_user)
    placed = EvaluationScore.objects.get(evaluation=evaluation, evaluator=vice).custom_axes

    client.force_login(principal_user)
    page = client.get(_url(teacher_user))
    rows = {key: value for key, _label, _max, value in page.context["axis_rows"]}
    assert rows == placed
    assert (page.context["is_editable"], page.context["can_approve"]) == (False, True)

    client.post(_url(teacher_user), _post_total(form, 0, "submitted"))
    evaluation.refresh_from_db()
    assert (evaluation.total_score, evaluation.evaluator_id, evaluation.status) == (
        92,
        vice.pk,
        "submitted",
    )
    assert not EvaluationScore.objects.filter(evaluator=principal_user).exists()
