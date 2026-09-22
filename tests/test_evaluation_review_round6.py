"""[LEGAL] عيوبُ المراجعة العدائيّة لموجة تقييم الأداء — جولة الإصلاح 5 (2026-09-17).

كلُّ اختبارٍ هنا سقط على الفرع قبل إصلاحه. والمراجع:

  - «02- النظام الوظيفي لموظفي المدارس.pdf» (قرار مجلس الوزراء 32/2019): المادة 15 صفحة
    الملفّ 10 — التقريرُ السنويّ «وفقاً للنماذج المعتمدة من الوزير» (02_staff_affairs.md:199)؛
    والمادة 16 — «يضع الرئيس المباشر تقييم أداء الموظف ويعتمد من مدير المدرسة»
    (02_staff_affairs.md:200)؛ والمادة 20 صفحتا الملفّ 12–13 — التظلّمُ «خلال خمسة عشر يوماً
    من تاريخ علمه»، فالنسخةُ التي أُعلن بها الموظّفُ هي محلُّ تظلّمه.
  - الاستمارةُ المطبوعة: «06- تقييم أداء الموظفين/استمارة تقييم المعلم والدليل التفسيري.pdf»،
    ونقلُها في `quality/ministry_appraisal_forms.json` (06_attendance_performance_review.md §2.4).
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
from django.contrib import admin as django_admin
from django.core.management import call_command
from django.test import RequestFactory
from django.utils import timezone

from core.models import AuditLog
from quality.evaluation_services import EvaluationRejectedError, save_evaluation
from quality.models import (
    EmployeeEvaluation,
    EvaluationAxis,
    EvaluationCycle,
    EvaluationScore,
    RoleEvaluationTemplate,
)
from tests.conftest import UserFactory
from tests.test_evaluation_review_round1 import (
    YEAR,
    _form_scores,
    _post_total,
    _seed,
    _staff,
    _url,
)


def _teacher_template(school):
    return RoleEvaluationTemplate.objects.get(
        school=school, role_name="teacher", academic_year=YEAR
    )


def _drift(school):
    """وزنُ محورٍ لا يطابق الاستمارةَ المطبوعة — كما لو صُحّح ملفُّ البيانات بعد البذر."""
    first = _teacher_template(school).axes.order_by("order").first()
    EvaluationAxis.objects.filter(pk=first.pk).update(weight=first.weight + 5)
    assert _teacher_template(school).matches_ministry_form() is False
    return first


def _report_on_template(school, employee, evaluator, form, status="draft", total=90):
    evaluation = EmployeeEvaluation.objects.create(
        school=school, employee=employee, evaluator=evaluator, academic_year=YEAR,
        period="S2", template=_teacher_template(school), status=status,
    )  # fmt: skip
    EvaluationScore.objects.create(
        evaluation=evaluation, evaluator=evaluator, custom_axes=_form_scores(form, total)
    )
    return evaluation


def _seed_output(school):
    out = StringIO()
    call_command(
        "seed_quality_templates", "--apply", "--school", school.code, "--year", YEAR, stdout=out
    )
    return out.getvalue()


# ── 1. لا يُقدَّم تقريرٌ سنويٌّ على قالبٍ لا يطابق الاستمارة، ولا يُعدّ، وله مخرج ──────────


@pytest.mark.django_db
def test_annual_report_is_not_saved_on_a_template_that_left_the_form(client, school, teacher_user):
    """
    المادة 15 (02_staff_affairs.md:199). مسودّةٌ عليها درجات تبقى على قالبها، فإن خرج القالبُ عن
    الاستمارة كان «تقديمُها» يُقبل ويُعلن نجاحاً — ثمّ لا يُعتمد أبداً.
    """
    form = _seed(school)
    vice = _staff(school, "vice_academic")
    evaluation = _report_on_template(school, teacher_user, vice, form)
    _drift(school)

    axes = [(a.key, a.label, a.weight) for a in _teacher_template(school).axes.all()]
    with pytest.raises(EvaluationRejectedError, match="استمارة"):
        save_evaluation(
            evaluation=evaluation, evaluator=vice, axes=axes, data=_post_total(form, 80)
        )
    evaluation.refresh_from_db()
    assert evaluation.status == "draft"

    client.force_login(vice)
    assert client.get(_url(teacher_user)).context["is_editable"] is False
    response = client.post(_url(teacher_user), _post_total(form, 80), follow=True)
    evaluation.refresh_from_db()
    assert evaluation.status == "draft"
    assert "تم تقديم" not in response.content.decode()


@pytest.mark.django_db
def test_no_approve_button_and_no_completion_for_a_report_off_the_form(
    client, school, principal_user, teacher_user
):
    """
    الاعتمادُ يرفض تقريراً على غير الاستمارة (المادة 15)، فلا يُعرض زرُّه، ولا تُحسب الدورةُ
    منجزةً به.
    """
    form = _seed(school)
    vice = _staff(school, "vice_academic")
    _report_on_template(school, teacher_user, vice, form, status="submitted")
    cycle = EvaluationCycle.objects.create(
        school=school, academic_year=YEAR, period="S2",
        deadline=timezone.localdate() + timedelta(days=30),
    )  # fmt: skip
    assert cycle.completion_rate > 0

    _drift(school)
    client.force_login(principal_user)
    assert client.get(_url(teacher_user)).context["can_approve"] is False
    assert EvaluationCycle.objects.get(pk=cycle.pk).completion_rate == 0


@pytest.mark.django_db
def test_seed_repairs_a_drifted_template_and_reopens_its_unapproved_reports(school, teacher_user):
    """
    المخرج: قالبٌ لم يُعتمد عليه تقريرٌ بعدُ يُعاد إلى الاستمارة بالبذر، والمُقدَّمُ عليه يرجع
    مسودّةً بلا مجموعٍ ولا مستوى، فيعيد واضعُه وضعَه على الأوزان المطبوعة. كان البذرُ يعدّه
    «مقفلاً» فلا سبيلَ إلى تصحيحه.
    """
    form = _seed(school)
    vice = _staff(school, "vice_academic")
    evaluation = _report_on_template(school, teacher_user, vice, form, status="submitted")
    EmployeeEvaluation.objects.filter(pk=evaluation.pk).update(total_score=90, rating="excellent")
    drifted = _drift(school)

    output = _seed_output(school)
    assert "مقفل" not in output
    assert "يُعاد مسودّةً: 1" in output
    assert _teacher_template(school).matches_ministry_form() is True
    assert EvaluationAxis.objects.get(pk=drifted.pk).weight == drifted.weight
    evaluation.refresh_from_db()
    assert (evaluation.status, evaluation.total_score, evaluation.rating) == ("draft", 0, "")
    assert AuditLog.objects.filter(object_id=str(evaluation.pk)).exists()


@pytest.mark.django_db
def test_seed_still_never_rewrites_a_template_with_an_approved_report(school, teacher_user):
    """ما اعتمده المديرُ (المادة 16) أُعلن به الموظّف — فقالبُه لا يُعاد كتابتُه."""
    form = _seed(school)
    vice = _staff(school, "vice_academic")
    approved = _report_on_template(school, teacher_user, vice, form, status="approved")
    drifted = _drift(school)

    assert "مقفل" in _seed_output(school)
    assert EvaluationAxis.objects.get(pk=drifted.pk).weight == drifted.weight + 5
    approved.refresh_from_db()
    assert approved.status == "approved"


# ── 2. لوحةُ الإدارة لا تغيّر نصَّ تقريرٍ معتمَد ولا تعليقَ الموظّف، وتسجّل ما تغيّره ───────


class _ChangedForm:
    def __init__(self, *changed):
        self.changed_data = list(changed)


def _admin_request():
    request = RequestFactory().post("/admin/")
    request.user = UserFactory(is_staff=True, is_superuser=True)
    return request


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["approved", "acknowledged"])
def test_admin_does_not_rewrite_the_texts_of_a_final_report(school, teacher_user, status):
    """
    النسخةُ التي اعتمدها المدير (المادة 16) وأُعلن بها الموظّفُ هي محلُّ تظلّمه (المادة 20)؛
    ومسارُ الشاشة يرفض أيَّ تعديلٍ بعد الاعتماد. وتعليقُ الموظّف كلامُه هو، لا يُحرَّر عنه.
    """
    form = _seed(school)
    vice = _staff(school, "vice_academic")
    evaluation = _report_on_template(school, teacher_user, vice, form, status=status)
    EmployeeEvaluation.objects.filter(pk=evaluation.pk).update(
        improvements="كما أُعلن", employee_comment="تعليقي"
    )
    evaluation.refresh_from_db()
    model_admin = django_admin.site._registry[EmployeeEvaluation]
    request = _admin_request()

    readonly = set(model_admin.get_readonly_fields(request, evaluation))
    assert {"strengths", "improvements", "goals_next", "employee_comment"} <= readonly

    evaluation.improvements = "نصٌّ آخر"
    evaluation.employee_comment = ""
    model_admin.save_model(
        request, evaluation, _ChangedForm("improvements", "employee_comment"), change=True
    )
    evaluation.refresh_from_db()
    assert (evaluation.improvements, evaluation.employee_comment) == ("كما أُعلن", "تعليقي")


@pytest.mark.django_db
def test_admin_text_correction_on_a_draft_is_audited(school, teacher_user):
    """ما بقي للوحة (نصوصُ المسودّة، وتواريخُ التظلّم) يُكتب في سجلّ التدقيق كمسارات الشاشة."""
    form = _seed(school)
    vice = _staff(school, "vice_academic")
    evaluation = _report_on_template(school, teacher_user, vice, form, status="draft")
    model_admin = django_admin.site._registry[EmployeeEvaluation]
    request = _admin_request()

    readonly = set(model_admin.get_readonly_fields(request, evaluation))
    assert "strengths" not in readonly
    assert "employee_comment" in readonly

    evaluation.strengths = "تصحيحٌ إملائيّ"
    model_admin.save_model(request, evaluation, _ChangedForm("strengths"), change=True)
    evaluation.refresh_from_db()
    assert evaluation.strengths == "تصحيحٌ إملائيّ"
    log = AuditLog.objects.get(object_id=str(evaluation.pk), user=request.user)
    assert log.changes["strengths"] == ["", "تصحيحٌ إملائيّ"]
