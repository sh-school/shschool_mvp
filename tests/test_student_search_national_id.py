"""[SECURITY] W-20261004-004: بحثُ الطلاب لا يمكّن من تخمين الرقم الشخصيّ بإضافة أرقام.

كان `/api/students/search/` يطابق `national_id__icontains` ويعرض الاسم، فموظفٌ غيرُ مقيَّدٍ بجناحٍ يضيف رقماً رقماً ويرى الاسمَ يضيق
حتى يستخرج رقمَ أيّ طالب. والآن المطابقةُ بالتساوي التامّ: رقمٌ كاملٌ يملكه السائلُ يُؤكَّد، وأيُّ جزءٍ منه لا يجد شيئاً.
البحثُ بالاسم كما كان.
"""

import pytest
from django.urls import reverse

from core.models import StudentEnrollment
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)
from tests.test_period_register import klass, supervisor, year  # noqa: F401 — تجهيزاتُ الجناح نفسُها

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


# ── بحثُ الطالب في أجنحتي: بالاسم وحده لكلّ الأدوار (W-20261012-002، قرار المالك D-396م) ──
# البحثُ بجزءٍ من الرقم مع ظهور الاسم يستخرج رقمَ طالبٍ خانةً خانةً؛ فلا رقمَ في البحث لا كاملاً ولا جزءاً.

WING_NID = "2930000" + "0123"  # رقمٌ اصطناعيّ للطالب في الجناح
WING_NAME = "سلمانُ الجناحيّ"
NOT_FOUND = "لا طالبَ بهذا الاسم في جناحك"


@pytest.fixture
def vice_admin(school):
    user = UserFactory(full_name="نائبٌ إداريّ للبحث")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="vice_admin"))
    return user


@pytest.fixture
def wing_student(school, seeded_calendar, klass, supervisor):  # noqa: F811 — `supervisor` يُنشئ الجناحَ ويربط به الشعبة
    kid = UserFactory(full_name=WING_NAME, national_id=WING_NID)
    StudentEnrollmentFactory(student=kid, class_group=klass)
    return kid


def _wing_search(client, q):
    return client.get(reverse("wings:student_search"), {"q": q})


@pytest.mark.parametrize("who", ["supervisor", "principal_user", "vice_admin"])
def test_the_wing_search_finds_by_name_for_every_role(client_as, request, wing_student, who):
    response = _wing_search(client_as(request.getfixturevalue(who)), "سلمان")

    assert response.status_code == 302
    assert response.url == reverse("wings:absence_file", args=[wing_student.id])


@pytest.mark.parametrize("who", ["supervisor", "principal_user", "vice_admin"])
def test_the_wing_search_never_matches_a_national_id_full_or_partial(
    client_as, request, wing_student, who
):
    """الرقمُ كاملاً وبدايتُه ونهايتُه ووسطُه لا تطابق لأيّ دور، وتظهر رسالةُ «لا طالبَ» لا ملفُّ الطالب."""
    client = client_as(request.getfixturevalue(who))

    for term in (WING_NID, WING_NID[:5], WING_NID[-4:], WING_NID[3:8]):
        response = _wing_search(client, term)
        assert response.status_code == 200, term
        body = response.content.decode()
        assert NOT_FOUND in body, term
        assert WING_NAME not in body, term


def test_the_empty_state_no_longer_invites_a_number_search(client_as, supervisor, wing_student):  # noqa: F811
    body = _wing_search(client_as(supervisor), "9999999999").content.decode()

    assert "أو الرقم" not in body and "الرقم الشخصيّ" not in body
