"""[W-20261012-032] REST المخالفات بنطاق الويب نفسِه: المعلّمُ يرى مخالفات طلاب جدوله وحدَهم.

كان `BehaviorListView.get_queryset` يُرجع كلَّ مخالفات المدرسة لأيّ معلّم، ولو طُلب `student_id` من خارج جدوله.
"""

from unittest.mock import patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from tests.conftest import (
    BehaviorInfractionFactory,
    MembershipFactory,
    RoleFactory,
    UserFactory,
)
from tests.test_behavior_views2 import teacher_student_link  # noqa: F401
from tests.test_supervisor_behavior_scope import _student  # noqa: F401

pytestmark = pytest.mark.django_db

URLS = ["/api/v1/behavior/", "/api/v1/behavior/?ordering=-date"]


def _ids(resp):
    body = resp.json()
    rows = body["results"] if isinstance(body, dict) else body
    return {str(r["id"]) for r in rows}


def _link(school, teacher, name):
    """طالبٌ في جدول المعلّم المذكور وحده."""
    from datetime import time

    from operations.models import ScheduleSlot
    from tests.conftest import ClassGroupFactory, StudentEnrollmentFactory

    student = UserFactory(full_name=name)
    MembershipFactory(user=student, school=school, role=RoleFactory(school=school, name="student"))
    cg = ClassGroupFactory(school=school)
    StudentEnrollmentFactory(student=student, class_group=cg)
    ScheduleSlot.objects.create(
        school=school,
        teacher=teacher,
        class_group=cg,
        day_of_week=1,
        period_number=2,
        start_time=time(8, 20),
        end_time=time(9, 5),
    )
    return student


@pytest.fixture
def two_teachers(school, teacher_user):
    other = UserFactory(full_name="معلّم آخر")
    MembershipFactory(user=other, school=school, role=RoleFactory(school=school, name="teacher"))
    mine = _link(school, teacher_user, "طالبي")
    theirs = _link(school, other, "طالبه")
    inf_mine = BehaviorInfractionFactory(school=school, student=mine, reported_by=teacher_user)
    inf_theirs = BehaviorInfractionFactory(school=school, student=theirs, reported_by=other)
    return other, mine, theirs, inf_mine, inf_theirs


@pytest.mark.parametrize("url", URLS)
def test_teacher_sees_only_infractions_of_own_students(client_as, teacher_user, two_teachers, url):
    _other, _mine, _theirs, inf_mine, inf_theirs = two_teachers
    got = _ids(client_as(teacher_user).get(url))
    assert str(inf_mine.pk) in got and str(inf_theirs.pk) not in got


def test_student_id_outside_the_schedule_returns_empty(client_as, teacher_user, two_teachers):
    _other, _mine, theirs, _a, inf_theirs = two_teachers
    resp = client_as(teacher_user).get(f"/api/v1/behavior/?student_id={theirs.pk}")
    assert resp.status_code == 200 and _ids(resp) == set()


def test_leadership_sees_the_whole_school(client_as, principal_user, two_teachers):
    _other, _m, _t, inf_mine, inf_theirs = two_teachers
    assert {str(inf_mine.pk), str(inf_theirs.pk)} <= _ids(
        client_as(principal_user).get("/api/v1/behavior/")
    )


def test_legacy_alias_gives_the_same_result(client_as, teacher_user, two_teachers):
    from api.urls import urlpatterns  # noqa: F401 — المسار القديم هو نفسه `/api/v1/behavior/`

    assert _ids(client_as(teacher_user).get("/api/v1/behavior/")) == _ids(
        client_as(teacher_user).get("/api/v1/behavior/?ordering=-date")
    )


def test_user_without_the_capability_gets_403(client_as, teacher_user, two_teachers):
    with patch("api.permissions.has_capability", return_value=False):
        assert client_as(teacher_user).get("/api/v1/behavior/").status_code == 403


def test_student_role_gets_403(client_as, student_user):
    assert client_as(student_user).get("/api/v1/behavior/").status_code == 403


def test_query_count_does_not_grow_with_infractions(client_as, school, teacher_user, two_teachers):
    _o, mine, *_ = two_teachers
    client = client_as(teacher_user)

    def count():
        with CaptureQueriesContext(connection) as ctx:
            assert client.get("/api/v1/behavior/").status_code == 200
        return len(ctx)

    count()  # تسخين (جلسة/تقويم)
    before = count()
    for _ in range(6):
        BehaviorInfractionFactory(school=school, student=mine, reported_by=teacher_user)
    assert count() == before
