"""[SECURITY] W-20261004-004: بحثُ الطلاب لا يمكّن من تخمين الرقم الشخصيّ بإضافة أرقام.

كان `/api/students/search/` يطابق `national_id__icontains` ويعرض الاسم، فموظفٌ غيرُ مقيَّدٍ بجناحٍ يضيف رقماً رقماً ويرى الاسمَ يضيق
حتى يستخرج رقمَ أيّ طالب. والآن المطابقةُ بالتساوي التامّ: رقمٌ كاملٌ يملكه السائلُ يُؤكَّد، وأيُّ جزءٍ منه لا يجد شيئاً.
البحثُ بالاسم كما كان.
"""

import pytest
from django.urls import reverse

from core.models import StudentEnrollment
from tests.conftest import ClassGroupFactory, StudentEnrollmentFactory, UserFactory

pytestmark = pytest.mark.django_db

NATIONAL_ID = "29400000077"
NAME = "طالبٌ للبحث الاختباريّ"


@pytest.fixture
def student(school):
    group = ClassGroupFactory(school=school)
    kid = UserFactory(full_name=NAME, national_id=NATIONAL_ID)
    StudentEnrollmentFactory(student=kid, class_group=group)
    assert StudentEnrollment.objects.filter(student=kid, is_active=True).exists()
    return kid


def _search(client, principal_user, q):
    response = client.get(reverse("api_student_search"), {"q": q})
    assert response.status_code == 200
    return response.json()["results"]


def test_the_exact_full_national_id_still_finds_the_student(client_as, principal_user, student):
    results = _search(client_as(principal_user), principal_user, NATIONAL_ID)
    assert [r["id"] for r in results] == [str(student.id)]


@pytest.mark.parametrize("length", range(2, len(NATIONAL_ID)))
def test_any_partial_national_id_finds_nothing_so_it_cannot_be_guessed_digit_by_digit(
    client_as, principal_user, student, length
):
    """أيُّ بدايةٍ أو وسطٍ أو نهايةٍ من الرقم (2..10 خانات) لا تُرجع شيئاً."""
    client = client_as(principal_user)
    for fragment in (
        NATIONAL_ID[:length],
        NATIONAL_ID[-length:],
        NATIONAL_ID[1 : 1 + length],
    ):
        assert _search(client, principal_user, fragment) == [], fragment


def test_the_result_never_carries_the_unmasked_national_id(client_as, principal_user, student):
    results = _search(client_as(principal_user), principal_user, NATIONAL_ID)
    assert results and all(r["national_id"] != NATIONAL_ID for r in results)


def test_search_by_name_is_unchanged(client_as, principal_user, student):
    results = _search(client_as(principal_user), principal_user, "للبحث الاختباريّ")
    assert [r["id"] for r in results] == [str(student.id)]
