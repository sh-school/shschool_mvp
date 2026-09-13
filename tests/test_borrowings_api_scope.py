"""[SECURITY] سجلُّ الاستعارات: المدرسةُ كلُّها لأمين المكتبة والقيادة، ولغيرهم ما يخصّهم.

كان ``/api/v1/library/borrowings/`` بـ``IsAuthenticated`` واستعلامٍ مقيَّدٍ بالمدرسة وحدَها،
ويقبل ``?student_id=`` — فأيُّ حسابٍ يقرأ من استعار ماذا ومتى تأخّر (مراجعةُ 2026-09-13، ن٥).
والشاشاتُ نفسُها تجعل إدارةَ الإعارة لأمين المكتبة وحدَه.
"""

import pytest
from django.test import Client
from django.utils import timezone

from core.models import ParentStudentLink
from tests.conftest import (
    BookBorrowingFactory,
    LibraryBookFactory,
    MembershipFactory,
    RoleFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db
URL = "/api/v1/library/borrowings/"


def _member(school, role_name):
    user = UserFactory()
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role_name))
    return user


def _ids(user, **params):
    client = Client()
    client.force_login(user)
    response = client.get(URL, params)
    assert response.status_code == 200
    return {row["id"] for row in response.json()["results"]}


@pytest.fixture
def loans(school):
    """استعارتان لطالبين مختلفين في المدرسة نفسِها."""
    book = LibraryBookFactory(school=school)
    reader = _member(school, "student")
    other = _member(school, "student")
    return {
        "reader": reader,
        "other": other,
        "mine": str(BookBorrowingFactory(book=book, user=reader).id),
        "theirs": str(BookBorrowingFactory(book=book, user=other).id),
    }


def test_a_student_sees_only_their_own_loans(school, loans):
    assert _ids(loans["reader"]) == {loans["mine"]}


def test_asking_for_another_student_by_id_returns_nothing(school, loans):
    assert _ids(loans["reader"], student_id=loans["other"].id) == set()


@pytest.mark.parametrize("role", ["services_worker", "teacher", "bus_supervisor"])
def test_staff_outside_the_library_see_no_one_elses_loans(school, loans, role):
    assert _ids(_member(school, role)) == set()


@pytest.mark.parametrize("role", ["librarian", "principal", "vice_admin"])
def test_the_library_and_leadership_see_the_whole_school(school, loans, role):
    assert _ids(_member(school, role)) == {loans["mine"], loans["theirs"]}


def test_a_parent_sees_their_childs_loans_only(school, loans):
    parent = _member(school, "parent")
    parent.consent_given_at = timezone.now()
    parent.save(update_fields=["consent_given_at"])
    ParentStudentLink.objects.create(school=school, parent=parent, student=loans["reader"])

    assert _ids(parent) == {loans["mine"]}
