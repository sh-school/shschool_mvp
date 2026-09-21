"""[LEGAL] شاشةُ التظلّم من تقرير تقييم الأداء — المادة 20 (صفحتا الملفّ 12–13).

«يُعلن الموظف بنسخة من تقرير تقييم الأداء، ويجوز للموظف أن يتظلم منه إلى لجنة موظفي المدارس
خلال خمسة عشر يوماً من تاريخ علمه، وتبت اللجنة في التظلم خلال ثلاثين يوماً من تاريخ تقديمه،
ويعتبر مضي المدة دون إخطار الموظف بتعديل التقرير بمثابة قرار بالرفض، ويكون قرار اللجنة في
التظلم نهائياً بعد اعتماده من الوزير، ولا يعتبر التقرير نهائياً إلا بعد انقضاء ميعاد التظلم
منه أو البت فيه» (`02_staff_affairs.md:211`).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from quality.evaluation_services import (
    EvaluationRejectedError,
    file_grievance,
    grievance_stage,
    record_grievance_decision,
)
from quality.models import EmployeeEvaluation
from tests.test_evaluation_review_round1 import YEAR, _staff

REASON = "أرى أنّ درجةَ الالتزام لا تعكس حضوري الفعليّ هذا العام."


def _known_days_ago(school, employee, evaluator, days, **extra):
    """تقريرٌ معتمَدٌ أقرّ الموظّفُ باستلامه قبل `days` يوماً."""
    then = timezone.now() - timedelta(days=days)
    return EmployeeEvaluation.objects.create(
        school=school, employee=employee, evaluator=evaluator, academic_year=YEAR,
        period="S1", status="acknowledged", approved_at=then - timedelta(days=1),
        acknowledged_at=then, total_score=80, rating="very_good", **extra,
    )  # fmt: skip


@pytest.fixture
def vice(school):
    return _staff(school, "vice_academic", "النائب الأكاديمي")


@pytest.mark.django_db
def test_stage_before_knowledge_is_waiting_for_the_acknowledgement():
    ev = EmployeeEvaluation(status="approved")
    assert grievance_stage(ev).code == "unknown"


@pytest.mark.django_db
def test_stage_follows_article_20(school, teacher_user, vice):
    today = timezone.localdate()
    ev = _known_days_ago(school, teacher_user, vice, 3)
    stage = grievance_stage(ev, today)
    assert (stage.code, stage.days_left, stage.final) == ("open", 12, False)

    ev.acknowledged_at = timezone.now() - timedelta(days=20)
    assert grievance_stage(ev, today).code == "closed"
    assert grievance_stage(ev, today).final is True

    ev.acknowledged_at = timezone.now() - timedelta(days=5)
    ev.grievance_submitted_on = today - timedelta(days=2)
    stage = grievance_stage(ev, today)
    assert (stage.code, stage.days_left) == ("filed", 28)

    ev.grievance_submitted_on = today - timedelta(days=31)
    ev.acknowledged_at = timezone.now() - timedelta(days=40)
    assert grievance_stage(ev, today).code == "lapsed"

    ev.grievance_submitted_on = today - timedelta(days=3)
    ev.acknowledged_at = timezone.now() - timedelta(days=10)
    ev.grievance_decided_on = today - timedelta(days=1)
    ev.grievance_outcome = "rejected"
    assert grievance_stage(ev, today).code == "decided"
    assert grievance_stage(ev, today).final is False

    ev.grievance_decision_approved_on = today
    stage = grievance_stage(ev, today)
    assert (stage.code, stage.final) == ("approved", True)


@pytest.mark.django_db
def test_the_employee_files_once_with_a_written_reason(client, school, teacher_user, vice):
    ev = _known_days_ago(school, teacher_user, vice, 3)
    client.force_login(teacher_user)
    url = reverse("file_evaluation_grievance", kwargs={"eval_id": ev.pk})

    assert client.post(url, {"reason": "قصير"}, follow=True).status_code == 200
    ev.refresh_from_db()
    assert ev.grievance_submitted_on is None

    client.post(url, {"reason": REASON})
    ev.refresh_from_db()
    assert ev.grievance_submitted_on == timezone.localdate()
    assert ev.grievance_reason == REASON

    client.post(url, {"reason": REASON + " مرّةً ثانية."})
    ev.refresh_from_db()
    assert ev.grievance_reason == REASON


@pytest.mark.django_db
def test_no_grievance_after_the_deadline_or_before_knowledge(school, teacher_user, vice):
    late = _known_days_ago(school, teacher_user, vice, 16)
    with pytest.raises(EvaluationRejectedError, match="انقضى ميعادُ التظلّم"):
        file_grievance(evaluation=late, employee=teacher_user, reason=REASON)

    unknown = EmployeeEvaluation.objects.create(
        school=school, employee=teacher_user, evaluator=vice, academic_year=YEAR,
        period="S2", status="approved", approved_at=timezone.now(),
    )  # fmt: skip
    with pytest.raises(EvaluationRejectedError, match="أقرَّ باستلامه"):
        file_grievance(evaluation=unknown, employee=teacher_user, reason=REASON)


@pytest.mark.django_db
def test_only_the_owner_of_the_report_can_file(client, school, teacher_user, vice):
    ev = _known_days_ago(school, teacher_user, vice, 2)
    other = _staff(school, "teacher", "زميل")
    client.force_login(other)

    response = client.post(
        reverse("file_evaluation_grievance", kwargs={"eval_id": ev.pk}), {"reason": REASON}
    )

    assert response.status_code == 404
    ev.refresh_from_db()
    assert ev.grievance_submitted_on is None


@pytest.mark.django_db
def test_my_evaluations_offers_the_form_only_while_the_window_is_open(
    client, school, teacher_user, vice
):
    ev = _known_days_ago(school, teacher_user, vice, 2)
    client.force_login(teacher_user)

    html = client.get(reverse("my_evaluations")).content.decode()
    assert reverse("file_evaluation_grievance", kwargs={"eval_id": ev.pk}) in html
    assert "باب التظلّم مفتوح" in html

    ev.acknowledged_at = timezone.now() - timedelta(days=40)
    ev.save(update_fields=["acknowledged_at"])
    html = client.get(reverse("my_evaluations")).content.decode()
    assert reverse("file_evaluation_grievance", kwargs={"eval_id": ev.pk}) not in html
    assert "انقضى ميعاد التظلّم" in html


@pytest.mark.django_db
def test_only_the_principal_sees_the_grievances(client, school, principal_user, teacher_user, vice):
    ev = _known_days_ago(
        school, teacher_user, vice, 4, grievance_submitted_on=timezone.localdate(),
        grievance_reason=REASON,
    )  # fmt: skip
    url = reverse("evaluation_grievances") + f"?year={YEAR}"

    client.force_login(vice)
    assert client.get(url).status_code == 403

    client.force_login(principal_user)
    response = client.get(url)
    assert response.status_code == 200
    body = response.content.decode()
    assert teacher_user.full_name in body and REASON in body
    assert reverse("record_grievance_decision", kwargs={"eval_id": ev.pk}) in body


@pytest.mark.django_db
def test_the_principal_records_the_committee_decision_then_the_ministers_approval(
    client, school, principal_user, teacher_user, vice
):
    today = timezone.localdate()
    ev = _known_days_ago(
        school, teacher_user, vice, 6, grievance_submitted_on=today - timedelta(days=3),
        grievance_reason=REASON,
    )  # fmt: skip
    client.force_login(principal_user)
    url = reverse("record_grievance_decision", kwargs={"eval_id": ev.pk})

    client.post(url, {"approved_on": today.isoformat()})
    ev.refresh_from_db()
    assert ev.grievance_decision_approved_on is None  # يُعتمد قرارٌ مدوَّن

    client.post(url, {"outcome": "rejected", "decided_on": (today - timedelta(days=1)).isoformat()})
    ev.refresh_from_db()
    assert (ev.grievance_outcome, ev.is_final(today)) == ("rejected", False)

    client.post(url, {"approved_on": today.isoformat()})
    ev.refresh_from_db()
    assert ev.grievance_decision_approved_on == today
    assert ev.is_final(today) is True

    client.post(url, {"outcome": "modified", "decided_on": today.isoformat()})
    ev.refresh_from_db()
    assert ev.grievance_outcome == "rejected"  # ما دُوِّن لا يُعاد كتابتُه


@pytest.mark.django_db
def test_a_non_principal_cannot_record_and_dates_must_follow_the_sequence(
    school, principal_user, teacher_user, vice
):
    today = timezone.localdate()
    ev = _known_days_ago(
        school, teacher_user, vice, 6, grievance_submitted_on=today - timedelta(days=3),
        grievance_reason=REASON,
    )  # fmt: skip
    with pytest.raises(EvaluationRejectedError, match="لمدير المدرسة"):
        record_grievance_decision(
            evaluation=ev, recorder=vice, decided_on=today, outcome="rejected", approved_on=None
        )
    with pytest.raises(EvaluationRejectedError, match="قبل تقديم التظلّم"):
        record_grievance_decision(
            evaluation=ev, recorder=principal_user, outcome="rejected", approved_on=None,
            decided_on=today - timedelta(days=5),
        )  # fmt: skip
    with pytest.raises(EvaluationRejectedError, match="اختر قرارَ اللجنة"):
        record_grievance_decision(
            evaluation=ev, recorder=principal_user, decided_on=today, outcome="", approved_on=None
        )
    ev.refresh_from_db()
    assert ev.grievance_decided_on is None


@pytest.mark.django_db
def test_the_platform_developer_sees_the_grievances_but_cannot_record(
    client, school, teacher_user, vice
):
    """مطوّرُ المنصّة (superuser) يرى ما يراه المدير للعرض وحدَه؛ التدوينُ لمدير المدرسة."""
    from tests.conftest import MembershipFactory, RoleFactory, UserFactory

    ev = _known_days_ago(
        school, teacher_user, vice, 4, grievance_submitted_on=timezone.localdate(),
        grievance_reason=REASON,
    )  # fmt: skip
    dev = UserFactory(is_superuser=True, is_staff=True, full_name="مطوّر المنصّة")
    MembershipFactory(
        user=dev, school=school, role=RoleFactory(school=school, name="platform_developer")
    )
    client.force_login(dev)

    response = client.get(reverse("evaluation_grievances") + f"?year={YEAR}")
    body = response.content.decode()
    assert response.status_code == 200
    assert REASON in body and "عرضٌ فقط" in body
    assert reverse("record_grievance_decision", kwargs={"eval_id": ev.pk}) not in body

    client.post(
        reverse("record_grievance_decision", kwargs={"eval_id": ev.pk}),
        {"outcome": "rejected", "decided_on": timezone.localdate().isoformat()},
    )
    ev.refresh_from_db()
    assert ev.grievance_decided_on is None


@pytest.mark.django_db
def test_the_platform_developer_cannot_act_as_the_principal(school, teacher_user, vice):
    """
    مفتاحُ التجربة سُحب (2026-09-21، بقرار المالك): مطوّرُ المنصّة (superuser) يرى شاشةَ التظلّمات
    للعرض، لكنّ اعتمادَ التقرير وتدوينَ الاستلام وقرارَ اللجنة لمدير المدرسة بعضويّة الدور وحدَه.
    """
    from quality.evaluation_services import approve_evaluation, record_receipt_on_refusal
    from tests.conftest import MembershipFactory, RoleFactory, UserFactory

    dev = UserFactory(is_superuser=True, is_staff=True, full_name="مطوّر المنصّة")
    MembershipFactory(
        user=dev, school=school, role=RoleFactory(school=school, name="platform_developer")
    )
    submitted = EmployeeEvaluation.objects.create(
        school=school, employee=teacher_user, evaluator=vice, academic_year=YEAR,
        period="S2", status="submitted", total_score=70,
    )  # fmt: skip
    with pytest.raises(EvaluationRejectedError, match="لمدير المدرسة"):
        approve_evaluation(evaluation=submitted, approver=dev)

    approved = _known_days_ago(school, teacher_user, vice, 2)
    with pytest.raises(EvaluationRejectedError, match="لمدير المدرسة"):
        record_receipt_on_refusal(
            evaluation=approved, recorder=dev, received_on=timezone.localdate()
        )
