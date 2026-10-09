"""[SCHEDULE] شريطُ تقدّم توليد V2 في صفحة الجدولة الذكية (W-20261009-022، P0 بأمر المالك).

القالبُ يرسم الشريطَ في كتلة التوليد الجاري فقط، ويحمل رابطَ نقطة التقدّم لهذا التوليد بعينه؛
والسكربتُ الخارجيّ (لا مضمَّن: سقّاطةُ السكربتات المضمَّنة) يستطلعها كلَّ 5 ثوانٍ ويعرض
المنقضي والمتبقّي والحلولَ والهدفَ والحالةَ النهائية. العقدُ من `progress.read_progress`.
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


@pytest.mark.django_db
def test_a_running_generation_renders_the_bar_pointing_at_its_own_endpoint(
    client_as, principal, school, assignment
):
    gen = ScheduleGeneration.objects.create(school=school, academic_year=YEAR, status="running")

    body = _page(client_as, principal)

    assert 'id="gen-progress"' in body
    assert f'data-url="{reverse("schedule_v2_progress", args=[gen.id])}"' in body
    assert 'role="meter"' in body, "الشريطُ مقياسٌ يقرؤه قارئُ الشاشة"
    assert "js/schedule-v2-progress" in body
    for field in ("elapsed", "remaining", "solutions", "objective", "final", "offline"):
        assert f'data-gp="{field}"' in body, field


@pytest.mark.django_db
def test_a_queued_generation_also_gets_the_bar(client_as, principal, school, assignment):
    ScheduleGeneration.objects.create(school=school, academic_year=YEAR, status="queued")

    assert 'id="gen-progress"' in _page(client_as, principal)


@pytest.mark.django_db
def test_no_bar_when_nothing_is_generating(client_as, principal, school, assignment):
    ScheduleGeneration.objects.create(school=school, academic_year=YEAR, status="draft")

    assert 'id="gen-progress"' not in _page(client_as, principal)


@pytest.mark.django_db
def test_the_endpoint_gives_the_script_every_field_it_reads(client_as, principal, school):
    gen = ScheduleGeneration.objects.create(school=school, academic_year=YEAR, status="running")
    tracker = progress.ProgressTracker(gen.pk, max_seconds=900)
    tracker.on_solution(objective=17918, bound=-189)
    tracker.publish()

    data = client_as(principal).get(reverse("schedule_v2_progress", args=[gen.id])).json()

    for key in (
        "state_label",
        "elapsed_s",
        "max_s",
        "remaining_s",
        "objective",
        "gap_pct",
        "solutions",
        "generation_status",
        "error",
    ):
        assert key in data, key
        assert f"d.{key}" in JS or key == "gap_pct" and "d.gap_pct" in JS, key
    assert data["objective"] == 17918 and data["solutions"] == 1


@pytest.mark.django_db
def test_a_failed_generation_reports_its_error_text(client_as, principal, school):
    gen = ScheduleGeneration.objects.create(
        school=school, academic_year=YEAR, status="failed", error_message="توقّف العاملُ"
    )

    data = client_as(principal).get(reverse("schedule_v2_progress", args=[gen.id])).json()

    assert data["done"] is True and data["generation_status"] == "failed"
    assert data["error"] == "توقّف العاملُ"


def test_the_script_polls_every_five_seconds_and_stops_after_five_misses():
    assert "INTERVAL = 5000" in JS
    assert "MAX_MISSES = 5" in JS
    assert "innerHTML" not in JS, "نصوصُ الخادم تدخل بـtextContent وحدَها"
