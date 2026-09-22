"""[LEGAL] عيوبُ المراجعة العدائيّة لموجة تقييم الأداء (جولة الإصلاح 4، 2026-09-16).

كلُّ اختبارٍ هنا سقط على الفرع قبل إصلاحه. والمراجع:

  - «02- النظام الوظيفي لموظفي المدارس.pdf» (قرار مجلس الوزراء 32/2019): المادة 15 صفحة
    الملفّ 10 — «وفقاً للنماذج المعتمدة من الوزير» (02_staff_affairs.md:199)؛ والمادة 20
    صفحتا الملفّ 12–13 — «ويجوز للموظف أن يتظلم منه ... خلال خمسة عشر يوماً من تاريخ علمه،
    وتبت اللجنة في التظلم خلال ثلاثين يوماً من تاريخ تقديمه ... ويكون قرار اللجنة في
    التظلم نهائياً بعد اعتماده من الوزير».
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import model_to_dict
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from quality.models import EmployeeEvaluation
from tests.conftest import UserFactory
from tests.test_evaluation_review_round1 import YEAR, _weighted_evaluation

# ── 1. تواريخُ التظلّم على تسلسل المادة 20 ────────────────────────────────────────

KNOWN_ON = date(2026, 6, 20)


def _acknowledged(school, employee, evaluator, **fields):
    return EmployeeEvaluation.objects.create(
        school=school, employee=employee, evaluator=evaluator, academic_year=YEAR,
        period="S2", status="acknowledged",
        acknowledged_at=timezone.make_aware(datetime.combine(KNOWN_ON, time(10))), **fields,
    )  # fmt: skip


@pytest.mark.django_db
def test_minister_approval_without_a_grievance_does_not_end_the_employees_window(
    school, principal_user, teacher_user
):
    """
    المادة 20: لا نهائيّةَ قبل «انقضاء ميعاد التظلم منه أو البت فيه» — واعتمادُ الوزير
    لقرار «اللجنة في التظلم» لا يكون بلا تظلّم، ولا قبل تقديمه، ولا في يومٍ لم يأتِ بعد.
    """
    evaluation = _acknowledged(school, teacher_user, principal_user)
    evaluation.grievance_decision_approved_on = KNOWN_ON
    assert evaluation.is_final(today=KNOWN_ON) is False
    assert evaluation.is_final(today=KNOWN_ON + timedelta(days=15)) is False
    assert evaluation.is_final(today=KNOWN_ON + timedelta(days=16)) is True

    evaluation.grievance_submitted_on = KNOWN_ON + timedelta(days=2)
    evaluation.grievance_decided_on = KNOWN_ON + timedelta(days=5)
    evaluation.grievance_decision_approved_on = KNOWN_ON + timedelta(days=40)
    assert evaluation.is_final(today=KNOWN_ON + timedelta(days=10)) is False
    evaluation.grievance_decision_approved_on = KNOWN_ON + timedelta(days=1)
    assert evaluation.is_final(today=KNOWN_ON + timedelta(days=10)) is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("fields", "field"),
    [
        # اعتمادُ قرارٍ بلا تظلّم، وإخطارٌ بقرارٍ بلا تظلّم.
        ({"grievance_decision_approved_on": KNOWN_ON}, "grievance_decision_approved_on"),
        ({"grievance_decided_on": KNOWN_ON}, "grievance_decided_on"),
        # تظلّمٌ قبل العلم: «خلال خمسة عشر يوماً من تاريخ علمه».
        ({"grievance_submitted_on": KNOWN_ON - timedelta(days=1)}, "grievance_submitted_on"),
        # قرارٌ قبل التظلّم: «تبت اللجنة في التظلم خلال ثلاثين يوماً من تاريخ تقديمه».
        (
            {
                "grievance_submitted_on": KNOWN_ON + timedelta(days=3),
                "grievance_decided_on": KNOWN_ON + timedelta(days=2),
            },
            "grievance_decided_on",
        ),
        (
            {
                "grievance_submitted_on": KNOWN_ON + timedelta(days=3),
                "grievance_decided_on": KNOWN_ON + timedelta(days=4),
                "grievance_decision_approved_on": KNOWN_ON + timedelta(days=2),
            },
            "grievance_decision_approved_on",
        ),
    ],
    ids=["approved-alone", "decided-alone", "before-knowledge", "decided-first", "approved-first"],
)
def test_grievance_dates_out_of_article_20_order_are_rejected(
    school, principal_user, teacher_user, fields, field
):
    evaluation = _acknowledged(school, teacher_user, principal_user, **fields)
    with pytest.raises(ValidationError) as caught:
        evaluation.clean()
    assert field in caught.value.message_dict


@pytest.mark.django_db
def test_grievance_dates_cannot_be_in_the_future_or_on_an_unapproved_report(
    school, principal_user, teacher_user
):
    evaluation = _acknowledged(
        school, teacher_user, principal_user,
        grievance_submitted_on=timezone.localdate() + timedelta(days=1),
    )  # fmt: skip
    evaluation.acknowledged_at = timezone.now()
    with pytest.raises(ValidationError) as caught:
        evaluation.clean()
    assert "grievance_submitted_on" in caught.value.message_dict

    draft = EmployeeEvaluation.objects.create(
        school=school, employee=UserFactory(), evaluator=principal_user, academic_year=YEAR,
        period="S2", grievance_submitted_on=KNOWN_ON,
    )  # fmt: skip
    with pytest.raises(ValidationError) as caught:
        draft.clean()
    assert "grievance_submitted_on" in caught.value.message_dict

    # والتسلسلُ السليم مقبول.
    _acknowledged(
        school, UserFactory(), principal_user,
        grievance_submitted_on=KNOWN_ON + timedelta(days=3),
        grievance_decided_on=KNOWN_ON + timedelta(days=20),
        grievance_decision_approved_on=KNOWN_ON + timedelta(days=25),
    ).clean()  # fmt: skip


@pytest.mark.django_db
def test_admin_form_refuses_a_minister_approval_without_a_grievance(
    school, principal_user, teacher_user
):
    """حقولُ التظلّم تُحرَّر من لوحة الإدارة — فالفحصُ يبلغ نموذجَها."""
    evaluation = _acknowledged(school, teacher_user, principal_user)
    model_admin = admin.site._registry[EmployeeEvaluation]
    request = RequestFactory().get("/")
    request.user = UserFactory(is_superuser=True, is_staff=True)
    form_class = model_admin.get_form(request, evaluation)
    data = {
        name: "" if value is None else value
        for name, value in model_to_dict(evaluation, fields=list(form_class.base_fields)).items()
    }
    data["grievance_decision_approved_on"] = KNOWN_ON.isoformat()
    form = form_class(data=data, instance=evaluation)
    assert not form.is_valid()
    assert "grievance_decision_approved_on" in form.errors


# ── 2. متوسّطُ اللوحة على مجموعة التوزيع نفسها ────────────────────────────────────


@pytest.mark.django_db
def test_dashboard_average_is_over_the_same_annual_reports_as_the_levels(
    client, school, principal_user, teacher_user
):
    """
    المتوسّطُ بجوار مستويات المادة 16 في شريطٍ واحد: فهو متوسّطُ التقارير السنويّة التي
    تُعدّ فيها — لا متابعة S1 الداخليّة، ولا يُعدّ الموظّفُ مرّتين.
    """
    EmployeeEvaluation.objects.create(
        school=school, employee=teacher_user, evaluator=principal_user, academic_year=YEAR,
        period="S1", status="submitted", axis_professional=25, axis_commitment=25,
        axis_teamwork=25, axis_development=20,
    )  # fmt: skip
    client.force_login(principal_user)
    url = reverse("evaluation_dashboard") + f"?year={YEAR}"
    context = client.get(url).context
    assert (context["avg_score"], context["rating_dist"]) == (None, {})

    annual = _weighted_evaluation(school, teacher_user, principal_user, (60,))
    annual.recalculate_from_scores()
    context = client.get(url).context
    assert context["rating_dist"] == {"acceptable": 1}
    assert context["avg_score"] == 60
