"""[LEGAL] عيوبُ المراجعة العدائيّة لموجة تقييم الأداء (جولة الإصلاح 3، الدفعة الثالثة، 2026-09-16؛
وجولة الإصلاح 4، 2026-09-17: القالبُ لا يُحسب استمارةً إلّا إن طابقها، واللوحةُ لا تكتبه).

كلُّ اختبارٍ هنا سقط على الفرع قبل إصلاحه. والمراجع:

  - «02- النظام الوظيفي لموظفي المدارس.pdf» (قرار مجلس الوزراء 32/2019): المادة 15 صفحة
    الملفّ 10 — «وفقاً للنماذج المعتمدة من الوزير» (02_staff_affairs.md:199)؛ والمادة 16 صفحتا
    الملفّ 10–11 (مستوياتُ الأداء الخمسة)؛ والمادة 20 صفحتا الملفّ 12–13 — «وتبت اللجنة في
    التظلم خلال ثلاثين يوماً من تاريخ تقديمه، ويعتبر انقضاء الميعاد المذكور دون إخطار الموظف
    بتعديل التقرير بمثابة قرار بالرفض».
"""

from __future__ import annotations

import importlib
from datetime import timedelta

import pytest
from django.apps import apps as django_apps
from django.contrib import admin as django_admin
from django.test import RequestFactory

from quality.evaluation_services import EvaluationRejectedError, approve_evaluation, save_evaluation
from quality.models import (
    EmployeeEvaluation,
    EvaluationAxis,
    EvaluationScore,
    RoleEvaluationTemplate,
)
from tests.conftest import UserFactory
from tests.test_evaluation_review_round1 import (
    YEAR,
    _migration_0018_forward,
    _post_total,
    _seed,
    _staff,
    _url,
    _weighted_evaluation,
)
from tests.test_evaluation_review_round3 import _FOREIGN_KEYS
from tests.test_evaluation_review_round4 import KNOWN_ON, _acknowledged

# ── 1. الرفضُ الحكميُّ بعد الثلاثين لا يُلغيه إخطارٌ متأخّر ─────────────────────────


@pytest.mark.django_db
def test_late_committee_notice_does_not_reopen_a_deemed_rejection(
    school, principal_user, teacher_user
):
    """
    المادة 20 (صفحة الملفّ 13): «ويعتبر انقضاء الميعاد المذكور دون إخطار الموظف بتعديل التقرير
    بمثابة قرار بالرفض». فإخطارٌ يُدوَّن بعد الثلاثين لا يعيد التقريرَ مفتوحاً؛ والإخطارُ في
    الميعاد قرارُ لجنةٍ ينتظر اعتمادَ الوزير («نهائياً بعد اعتماده من الوزير»).
    """
    submitted = KNOWN_ON + timedelta(days=3)
    decision_by = submitted + timedelta(days=30)
    evaluation = _acknowledged(
        school, teacher_user, principal_user, grievance_submitted_on=submitted
    )
    assert evaluation.is_final(today=decision_by) is False
    assert evaluation.is_final(today=decision_by + timedelta(days=1)) is True

    evaluation.grievance_decided_on = decision_by + timedelta(days=19)
    assert evaluation.is_final(today=decision_by + timedelta(days=20)) is True

    evaluation.grievance_decided_on = decision_by
    assert evaluation.is_final(today=decision_by + timedelta(days=20)) is False


# ── 2. حفظُ المقيِّم على القالب يمرّ بثابت «لا مستوى خارج الاستمارة» ─────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("custom_axes", [_FOREIGN_KEYS, {}], ids=["foreign-keys", "empty"])
def test_saving_form_scores_beside_an_off_form_row_gives_no_article_16_level(
    school, teacher_user, custom_axes
):
    """
    المادة 15: التقريرُ السنويّ «وفقاً للنماذج المعتمدة من الوزير»، ومستوياتُ المادة 16 مستوياتُه.
    فصفُّ مقيِّمٍ آخر على مفاتيحَ غريبة يُبقي التقريرَ خارج الاستمارة وإن حفظ واضعُه درجاتِها.
    """
    form = _seed(school)
    template = RoleEvaluationTemplate.objects.get(
        school=school, role_name="teacher", academic_year=YEAR
    )
    vice = _staff(school, "vice_academic")
    evaluation = EmployeeEvaluation.objects.create(
        school=school, employee=teacher_user, evaluator=vice, academic_year=YEAR,
        period="S2", template=template, status="draft",
    )  # fmt: skip
    EvaluationScore.objects.create(
        evaluation=evaluation, evaluator=_staff(school, "coordinator"), custom_axes=custom_axes
    )
    axes = [(a.key, a.label, a.weight) for a in template.axes.all()]
    save_evaluation(evaluation=evaluation, evaluator=vice, axes=axes, data=_post_total(form, 90))
    evaluation.refresh_from_db()
    assert evaluation.has_form_scores() is False
    assert evaluation.rating == ""


# ── 3. الهجرة 0018: ما تغيّره يُسجَّل، وعكسُها يسترجعه ───────────────────────────


def _migration_0018_backward():
    module = importlib.import_module("quality.migrations.0018_employeeevaluation_five_level_rating")
    return module.Migration.operations[-1].reverse_code


def _backups():
    return django_apps.get_model("quality", "EvaluationLevelBackup").objects


@pytest.mark.django_db
def test_migration_0018_records_what_it_changes_and_its_reverse_restores_it(
    school, principal_user, teacher_user
):
    """
    صفُّ S2 مُقَرٌّ به على المحاور الأربعة (قبل الموجة): التقدّمُ يُفرغ مستواه (المادة 15)، لكنّه
    يسجّل ما كان — والعكسُ يعيده كما كان، وكذلك المجموعُ المرجَّح الذي أعاد كتابتَه.
    """
    other = _staff(school, "it_technician")
    legacy = EmployeeEvaluation.objects.create(
        school=school, employee=other, evaluator=principal_user, academic_year=YEAR,
        period="S2", status="acknowledged", axis_professional=21, axis_commitment=21,
        axis_teamwork=20, axis_development=20,
    )  # fmt: skip
    EmployeeEvaluation.objects.filter(pk=legacy.pk).update(total_score=82, rating="very_good")
    weighted = _weighted_evaluation(school, teacher_user, principal_user, (90, 89))
    EmployeeEvaluation.objects.filter(pk=weighted.pk).update(total_score=90, rating="excellent")

    _migration_0018_forward()(django_apps, None)
    legacy.refresh_from_db()
    weighted.refresh_from_db()
    assert (legacy.total_score, legacy.rating) == (82, "")
    assert (weighted.total_score, weighted.rating) == (89, "very_good")
    backup = _backups().get(evaluation_id=legacy.pk)
    assert (backup.old_total_score, backup.old_rating) == (82, "very_good")

    _migration_0018_backward()(django_apps, None)
    legacy.refresh_from_db()
    weighted.refresh_from_db()
    assert (legacy.total_score, legacy.rating) == (82, "very_good")
    assert (weighted.total_score, weighted.rating) == (90, "excellent")
    assert not _backups().exists()


@pytest.mark.django_db
def test_migration_0018_reverse_does_not_overwrite_a_row_changed_since(
    school, principal_user, teacher_user
):
    """صفٌّ تغيّر بعد التقدّم لا يُكتب فوقه ما سُجّل قبله — يُصنَّف بالعتبات القديمة."""
    weighted = _weighted_evaluation(school, teacher_user, principal_user, (90, 89))
    EmployeeEvaluation.objects.filter(pk=weighted.pk).update(total_score=90, rating="excellent")
    _migration_0018_forward()(django_apps, None)
    EmployeeEvaluation.objects.filter(pk=weighted.pk).update(total_score=70, rating="good")

    _migration_0018_backward()(django_apps, None)
    weighted.refresh_from_db()
    assert (weighted.total_score, weighted.rating) == (70, "good")


# ── 4. القالبُ لا يُحسب «استمارةً» إلّا إن طابق استمارةَ دوره في الملفّ الوزاريّ ─────────


def _superuser_request():
    request = RequestFactory().get("/admin/")
    request.user = UserFactory(is_staff=True, is_superuser=True)
    return request


@pytest.mark.django_db
def test_admin_writes_no_template_or_axis(school):
    """
    القوالبُ منسوخةٌ من الاستمارات السبع (`quality/ministry_appraisal_forms.json`) بأمر البذر
    وحده. فاللوحةُ كانت تضيف قالباً لدورٍ لا استمارةَ له، وتغيّر وزنَ محورٍ أو دورَ قالبٍ عليه
    تقييمات — فيُعتمد تقريرٌ سنويٌّ على غير «النماذج المعتمدة من الوزير» (المادة 15،
    02_staff_affairs.md:199).
    """
    _seed(school)
    template = RoleEvaluationTemplate.objects.get(
        school=school, role_name="teacher", academic_year=YEAR
    )
    request = _superuser_request()
    template_admin = django_admin.site._registry[RoleEvaluationTemplate]
    assert template_admin.has_add_permission(request) is False
    assert template_admin.has_change_permission(request, template) is False
    inline = template_admin.get_inline_instances(request, template)[0]
    assert inline.has_add_permission(request, template) is False
    assert inline.has_change_permission(request, template) is False
    assert inline.has_delete_permission(request, template) is False


@pytest.mark.django_db
def test_a_template_for_a_role_without_a_form_opens_no_annual_report(
    client, school, principal_user
):
    """
    ADR-0002 §6.6 بند 12: لا خانةَ للمنسّق في رأس أيٍّ من الاستمارات السبع. فقالبٌ له (من
    اللوحة أو من قاعدةٍ قديمة) لا يفتح تقريراً سنويّاً، ولا تُعدّ درجاتُه درجاتِ استمارة.
    """
    _seed(school)
    coordinator = _staff(school, "nurse")
    template = RoleEvaluationTemplate.objects.create(
        school=school, role_name="nurse", academic_year=YEAR
    )
    EvaluationAxis.objects.create(template=template, key="all", label="الأداء", weight=100)
    client.force_login(principal_user)
    assert client.get(_url(coordinator)).status_code == 409

    vice = _staff(school, "vice_academic")
    evaluation = EmployeeEvaluation.objects.create(
        school=school, employee=coordinator, evaluator=vice, academic_year=YEAR,
        period="S2", template=template, status="submitted",
    )  # fmt: skip
    EvaluationScore.objects.create(evaluation=evaluation, evaluator=vice, custom_axes={"all": 95})
    assert evaluation.has_form_scores() is False
    with pytest.raises(EvaluationRejectedError, match="استمارة"):
        approve_evaluation(evaluation=evaluation, approver=principal_user)


@pytest.mark.django_db
def test_a_seeded_template_with_a_changed_weight_is_not_the_form(
    client, school, principal_user, teacher_user
):
    """
    وزنُ محورٍ غُيِّر بعد البذر (قبل أن يُربط به تقييم) ليس وزنَ الاستمارة المطبوعة
    («استمارة تقييم المعلم والدليل التفسيري.pdf»، المنقولة في
    06_attendance_performance_review.md §2.3): فلا تقريرَ يُفتح عليه ولا يُعتمد.
    """
    form = _seed(school)
    template = RoleEvaluationTemplate.objects.get(
        school=school, role_name="teacher", academic_year=YEAR
    )
    first = template.axes.order_by("order").first()
    EvaluationAxis.objects.filter(pk=first.pk).update(weight=first.weight + 5)
    client.force_login(principal_user)
    assert client.get(_url(teacher_user)).status_code == 409

    vice = _staff(school, "vice_academic")
    evaluation = EmployeeEvaluation.objects.create(
        school=school, employee=teacher_user, evaluator=vice, academic_year=YEAR,
        period="S2", template=template, status="submitted",
    )  # fmt: skip
    EvaluationScore.objects.create(
        evaluation=evaluation, evaluator=vice, custom_axes={a.key: a.weight for a in form.axes}
    )
    assert evaluation.has_form_scores() is False
