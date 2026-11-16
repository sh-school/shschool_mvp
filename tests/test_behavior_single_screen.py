"""W-20261001-042: شاشةٌ واحدة لتسجيل المخالفة؛ المسارُ القديم يحوّل إليها لكلّ دورٍ يملك `behavior.record`."""

from datetime import time

import pytest
from django.urls import reverse

from core.capabilities import registry
from core.models import Wing
from core.permissions import expand_roles
from operations.models import ScheduleSlot, Subject
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)
from tests.test_period_register import klass, supervisor, year  # noqa: F401

pytestmark = pytest.mark.django_db

RECORD_ROLES = sorted(registry()["behavior.record"].expanded_roles)


def test_eleven_roles_hold_the_record_capability():
    assert len(RECORD_ROLES) == 11
    assert set(RECORD_ROLES) <= expand_roles(set(registry()["behavior.record"].roles))


@pytest.mark.parametrize("role_name", RECORD_ROLES)
def test_every_recording_role_is_sent_to_the_one_screen(client_as, school, role_name):
    user = UserFactory(full_name="مسجِّل")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role_name))

    resp = client_as(user).get(reverse("behavior:quick_log"), {"student_id": "5"})

    assert resp.status_code == 301
    assert resp["Location"] == reverse("behavior:report_infraction") + "?student=5"


def test_a_role_without_the_capability_is_refused_before_any_redirect(client_as, school):
    user = UserFactory(full_name="طالب")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="student"))

    assert client_as(user).get(reverse("behavior:quick_log")).status_code == 403


# ── بلاغ 5D5D (البند 2): الوصولُ إلى كشف السلوك دون تسجيل مخالفة ─────────────
# أرقامُ الهويّة اصطناعيّة (2900000000x) — حارسُ البيانات الشخصيّة يرفض غيرها.

VIEW_ONLY_ROLES = sorted(
    registry()["behavior.view"].expanded_roles
    - registry()["behavior.record"].expanded_roles
    - {"student", "parent"}
)


def _student(school, group, name, national_id):
    user = UserFactory(full_name=name, national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="student"))
    StudentEnrollmentFactory(student=user, class_group=group)
    return user


@pytest.fixture
def far_klass(school, seeded_calendar, year):
    """شعبةٌ في جناحٍ ثانٍ — ليست من شُعب المشرف."""
    wing = Wing.objects.create(school=school, code="w2", name="جناح 2", academic_year=year)
    return ClassGroupFactory(
        school=school, grade="G8", section="2", level_type="prep", academic_year=year, wing=wing
    )


@pytest.fixture
def mine(school, seeded_calendar, klass):
    return _student(school, klass, "طالبُ جناحي", "29000000001")


@pytest.fixture
def theirs(school, seeded_calendar, far_klass):
    return _student(school, far_klass, "طالبُ الجناح الآخر", "29000000002")


@pytest.fixture
def principal(school):
    user = UserFactory(full_name="مدير المدرسة")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="principal"))
    return user


class TestDashboardStudentSearch:
    def test_the_search_box_is_on_the_dashboard(
        self, client_as, school, seeded_calendar, supervisor
    ):
        resp = client_as(supervisor).get(reverse("behavior:dashboard"))

        assert b'name="q"' in resp.content
        assert resp.context["student_matches"] == []

    def test_the_supervisor_finds_only_his_wing(
        self, client_as, school, seeded_calendar, mine, theirs, supervisor
    ):
        resp = client_as(supervisor).get(reverse("behavior:dashboard"), {"q": "طالب"})

        assert [s.pk for s in resp.context["student_matches"]] == [mine.pk]

    def test_the_supervisor_cannot_reach_a_student_by_national_id(
        self, client_as, school, seeded_calendar, mine, theirs, supervisor
    ):
        resp = client_as(supervisor).get(reverse("behavior:dashboard"), {"q": "29000000002"})

        assert resp.context["student_matches"] == []

    def test_the_principal_finds_the_whole_school_by_id(
        self, client_as, school, seeded_calendar, mine, theirs, principal
    ):
        resp = client_as(principal).get(reverse("behavior:dashboard"), {"q": "29000000002"})

        assert [s.pk for s in resp.context["student_matches"]] == [theirs.pk]

    def test_each_result_opens_the_student_profile(
        self, client_as, school, seeded_calendar, mine, supervisor
    ):
        resp = client_as(supervisor).get(reverse("behavior:dashboard"), {"q": "جناحي"})

        profile = reverse("behavior:student_profile", kwargs={"student_id": mine.pk})
        assert profile in resp.content.decode()


class TestStudentProfileReportLink:
    def test_a_profile_with_no_infraction_links_to_the_report(
        self, client_as, school, seeded_calendar, mine, supervisor
    ):
        resp = client_as(supervisor).get(
            reverse("behavior:student_profile", kwargs={"student_id": mine.pk})
        )

        assert resp.status_code == 200
        assert list(resp.context["infractions"]) == []
        report = reverse("behavior:behavior_report", kwargs={"student_id": mine.pk})
        assert report in resp.content.decode()

    @pytest.mark.parametrize("role_name", VIEW_ONLY_ROLES)
    def test_a_role_that_cannot_record_sees_no_report_link(
        self, client_as, school, seeded_calendar, mine, klass, role_name
    ):
        user = UserFactory(full_name="مطّلع")
        MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role_name))
        # المعلّمُ ومساعدُه لا يريان إلا طلبةَ جدولهم: الشعبةُ في الجدول فيصل الطالبُ إلى الملف
        ScheduleSlot.objects.create(
            school=school,
            teacher=user,
            class_group=klass,
            subject=Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH"),
            day_of_week=0,
            period_number=1,
            start_time=time(7, 10),
            end_time=time(7, 55),
            academic_year=klass.academic_year,
            is_active=True,
        )

        resp = client_as(user).get(
            reverse("behavior:student_profile", kwargs={"student_id": mine.pk})
        )

        assert resp.status_code == 200
        report = reverse("behavior:behavior_report", kwargs={"student_id": mine.pk})
        assert report not in resp.content.decode()
