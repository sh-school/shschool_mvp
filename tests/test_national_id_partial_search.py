"""[SECURITY] البحثُ الجزئيُّ بالرقم الشخصيّ للإدارة وحدَها؛ والباقون بالتساوي التامّ.

#849 أغلق «التخمينَ رقماً رقماً» في `/api/students/search/` وحدَه وبقيت مواضعُ تبحث بالاحتواء. القرارُ (المالك، 2026-10-05):
التساوي التامُّ للجميع، والاحتواءُ للإدارة (`PARTIAL_ID_SEARCH_ROLES` + المشرفُ العامّ).
"""

import pytest
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse

from core.models import CustomUser
from core.privacy import may_search_id_partially, national_id_search_q
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

NATIONAL_ID = "29400000088"
NAME = "طالبٌ لاختبار البحث الجزئيّ"


@pytest.fixture
def student(school):
    kid = UserFactory(full_name=NAME, national_id=NATIONAL_ID)
    MembershipFactory(user=kid, school=school, role=RoleFactory(school=school, name="student"))
    StudentEnrollmentFactory(student=kid, class_group=ClassGroupFactory(school=school))
    return kid


def _ids(**kwargs):
    return list(CustomUser.objects.filter(national_id_search_q("national_id", **kwargs)))


# ── الدالّةُ نفسُها ──────────────────────────────────────────────────────────


def test_exact_match_finds_the_full_number(student):
    assert _ids(term=NATIONAL_ID) == [student]


@pytest.mark.parametrize("fragment", [NATIONAL_ID[:4], NATIONAL_ID[-4:], NATIONAL_ID[3:8]])
def test_a_fragment_finds_nothing_unless_partial_is_allowed(student, fragment):
    assert _ids(term=fragment) == []
    assert _ids(term=fragment, partial=True) == [student]


@pytest.mark.parametrize("term", ["", "   ", None])
def test_an_empty_term_never_matches_anyone(student, term):
    assert _ids(term=term) == []
    assert _ids(term=term, partial=True) == []


# ── من يجوز له ───────────────────────────────────────────────────────────────


def test_management_may_search_partially(principal_user):
    assert may_search_id_partially(principal_user) is True


def test_superuser_may_search_partially(db):
    assert may_search_id_partially(UserFactory(is_superuser=True)) is True


def test_other_staff_and_anonymous_may_not(teacher_user, coordinator_user):
    assert may_search_id_partially(teacher_user) is False
    assert may_search_id_partially(coordinator_user) is False
    assert may_search_id_partially(AnonymousUser()) is False
    assert may_search_id_partially(None) is False


# ── في الشاشة: قائمةُ الطلبة ─────────────────────────────────────────────────


def _list(client, q):
    response = client.get(reverse("student_affairs:student_list"), {"q": q, "status": "all"})
    assert response.status_code == 200
    return response.content.decode()


def test_management_finds_the_student_by_a_fragment(client_as, principal_user, student):
    assert NAME in _list(client_as(principal_user), NATIONAL_ID[-6:])


def test_a_coordinator_cannot_find_the_student_by_a_fragment(client_as, coordinator_user, student):
    assert NAME not in _list(client_as(coordinator_user), NATIONAL_ID[-6:])


def test_a_coordinator_still_finds_the_student_by_the_full_number(
    client_as, coordinator_user, student
):
    assert NAME in _list(client_as(coordinator_user), NATIONAL_ID)
