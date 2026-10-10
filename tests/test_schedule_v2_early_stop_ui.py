"""[SCHEDULE] الإيقافُ المبكّر لتوليد V2 من صفحة الجدولة الذكية (W-20261010-002).

زرُّ «إيقاف التوليد» القديمُ هو إيقافُ V1: يجعل الصفَّ «فشل» ولا يحفظ شيئاً، فيضيع أفضلُ حلٍّ في توليد V2.
فصفُّ V2 الجاري يعرض زرَّ الإيقاف المبكّر (v2-stop) بدلَه، ويُحوَّل إيقافُ V1 عليه إلى الإيقاف المبكّر.
"""

from pathlib import Path

import pytest
from django.urls import reverse

from operations.models import ScheduleGeneration, Subject, SubjectClassAssignment
from operations.scheduler_v2 import progress
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

YEAR = "2026-2027"
JS = (
    Path(__file__).resolve().parent.parent / "static" / "js" / "schedule-v2-progress.js"
).read_text(encoding="utf-8")


@pytest.fixture
def principal(school):
    role = RoleFactory(school=school, name="principal")
    user = UserFactory(full_name="مدير المدرسة")
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def assignment(school):
    role = RoleFactory(school=school, name="teacher")
    teacher = UserFactory(full_name="معلّم")
    MembershipFactory(user=teacher, school=school, role=role)
    subject = Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")
    group = ClassGroupFactory(school=school, grade="G9", level_type="prep", academic_year=YEAR)
    return SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=teacher,
        class_group=group,
        subject=subject,
        weekly_periods=5,
    )


def _page(client_as, user):
    return client_as(user).get(reverse("smart_schedule") + f"?year={YEAR}").content.decode()


def _v2_running(school):
    return ScheduleGeneration.objects.create(
        school=school,
        academic_year=YEAR,
        status="running",
        metrics={progress.KEY: {"state": "feasible", "solutions": 3}},
    )


@pytest.mark.django_db
def test_a_running_v2_row_shows_the_early_stop_button_not_the_v1_one(
    client_as, principal, school, assignment
):
    gen = _v2_running(school)

    body = _page(client_as, principal)

    assert 'data-gp="stop"' in body
    assert reverse("schedule_v2_stop", args=[gen.id]) in body
    assert "إيقاف مبكر (يحتفظ بأفضل حلّ)" in body
    assert reverse("stop_schedule_generation", args=[gen.id]) not in body


@pytest.mark.django_db
def test_a_running_v1_row_keeps_the_old_stop_form_and_has_no_early_stop(
    client_as, principal, school, assignment
):
    gen = ScheduleGeneration.objects.create(school=school, academic_year=YEAR, status="running")

    body = _page(client_as, principal)

    assert reverse("stop_schedule_generation", args=[gen.id]) in body
    assert 'data-gp="stop"' not in body


@pytest.mark.django_db
def test_v1_stop_on_a_v2_row_is_redirected_and_keeps_the_generation_running(
    client_as, principal, school, assignment
):
    gen = _v2_running(school)

    response = client_as(principal).post(reverse("stop_schedule_generation", args=[gen.id]))

    gen.refresh_from_db()
    assert response.status_code == 302
    assert gen.status == "running"
    assert gen.error_message == ""


@pytest.mark.django_db
def test_early_stop_endpoint_sets_the_flag_and_returns_409_once_finished(
    client_as, principal, school, assignment
):
    gen = _v2_running(school)
    url = reverse("schedule_v2_stop", args=[gen.id])

    first = client_as(principal).post(url)
    gen.refresh_from_db()

    assert first.status_code == 200
    assert gen.metrics[progress.STOP_KEY] is True

    ScheduleGeneration.objects.filter(pk=gen.pk).update(status="draft")
    assert client_as(principal).post(url).status_code == 409


@pytest.mark.django_db
def test_early_stop_requires_schedule_admin(client_as, school, assignment):
    gen = _v2_running(school)
    role = RoleFactory(school=school, name="teacher")
    other = UserFactory(full_name="معلّم آخر")
    MembershipFactory(user=other, school=school, role=role)

    response = client_as(other).post(reverse("schedule_v2_stop", args=[gen.id]))

    assert response.status_code == 403


def test_script_gates_the_button_on_solutions_and_handles_409():
    assert "d.solutions > 0" in JS
    assert "r.status === 409" in JS
    assert "X-CSRFToken" in JS
