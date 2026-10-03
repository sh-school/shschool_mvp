"""[STAFF] «المغادرون» من لا عضويّةَ كادرٍ نشطةً له — لا كلُّ من له صفٌّ منتهٍ (W-20261002-043).

كانت القائمةُ تُرشّح بوجود أيّ عضويّةٍ غير نشطة، فيظهر في «المغادرون» من غادر ثمّ أُعيد تعيينُه
بعضويّةٍ جديدة، ومن عُطّلت عضويّةٌ قديمةٌ له، وهو على رأس عمله. والمغادرةُ كانت تُنهي كلَّ أدوار
الشخص بضغطةٍ واحدة.
"""

import pytest
from django.urls import reverse
from django.utils import timezone

from core.models import Membership
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def principal(school):
    user = UserFactory(full_name="المدير")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="principal"))
    return user


def _staff(school, name, role="teacher", *, active=True):
    user = UserFactory(full_name=name)
    membership = MembershipFactory(
        user=user, school=school, role=RoleFactory(school=school, name=role), is_active=active
    )
    return user, membership


def _names(client, status):
    resp = client.get(reverse("staff_affairs:staff_list"), {"status": status})
    assert resp.status_code == 200
    return [row["full_name"] for row in resp.context["staff"]]


def test_a_person_with_an_old_ended_row_and_an_active_one_is_current_not_departed(
    client_as, school, principal
):
    user, _ = _staff(school, "عاملٌ أعيد تعيينُه")
    old_role = RoleFactory(school=school, name="coordinator")
    MembershipFactory(
        user=user, school=school, role=old_role, is_active=False, left_at=timezone.localdate()
    )
    client = client_as(principal)

    assert "عاملٌ أعيد تعيينُه" in _names(client, "current")
    assert "عاملٌ أعيد تعيينُه" not in _names(client, "left")


def test_a_manually_disabled_old_row_does_not_make_a_working_person_departed(
    client_as, school, principal
):
    user, _ = _staff(school, "عاملٌ بصفٍّ معطَّل")
    MembershipFactory(
        user=user,
        school=school,
        role=RoleFactory(school=school, name="specialist"),
        is_active=False,
    )
    client = client_as(principal)

    assert "عاملٌ بصفٍّ معطَّل" not in _names(client, "left")
    assert _names(client, "current").count("عاملٌ بصفٍّ معطَّل") == 1


def test_a_person_with_no_active_staff_row_is_listed_as_departed_once(client_as, school, principal):
    _staff(school, "غادر فعلاً", active=False)
    client = client_as(principal)

    assert _names(client, "left").count("غادر فعلاً") == 1
    assert "غادر فعلاً" not in _names(client, "current")


def test_a_guardian_row_never_makes_a_staff_member_departed(client_as, school, principal):
    user, _ = _staff(school, "معلّمٌ وليُّ أمر")
    MembershipFactory(
        user=user, school=school, role=RoleFactory(school=school, name="parent"), is_active=False
    )

    assert "معلّمٌ وليُّ أمر" not in _names(client_as(principal), "left")


# ── المغادرةُ بدورٍ محدَّد ──


def _two_roles(school):
    user, first = _staff(school, "ذو دورين")
    second = MembershipFactory(
        user=user, school=school, role=RoleFactory(school=school, name="coordinator")
    )
    return user, first, second


def _depart_post(client, user, **extra):
    return client.post(
        reverse("staff_affairs:staff_depart", args=[user.pk]),
        {
            "on": timezone.localdate().isoformat(),
            "reason": "transfer",
            "reference": "قرار 2026/1",
            "note": "",
            **extra,
        },
    )


def test_departing_a_person_with_two_roles_needs_an_explicit_choice(client_as, school, principal):
    user, first, second = _two_roles(school)

    resp = _depart_post(client_as(principal), user)

    assert resp.status_code == 302
    assert Membership.objects.filter(user=user, is_active=True).count() == 2


def test_departing_one_role_leaves_the_other_active(client_as, school, principal):
    user, first, second = _two_roles(school)

    _depart_post(client_as(principal), user, membership=str(second.pk))

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.is_active is True and second.is_active is False
    assert second.departure_reference == "قرار 2026/1"


def test_departing_all_roles_is_possible_but_explicit(client_as, school, principal):
    user, first, second = _two_roles(school)

    _depart_post(client_as(principal), user, membership="all")

    assert not Membership.objects.filter(user=user, is_active=True).exists()


def test_a_membership_of_someone_else_cannot_be_picked(client_as, school, principal):
    user, first, second = _two_roles(school)
    _, other = _staff(school, "آخر")

    _depart_post(client_as(principal), user, membership=str(other.pk))

    other.refresh_from_db()
    assert other.is_active is True
    assert Membership.objects.filter(user=user, is_active=True).count() == 2


def test_a_single_role_person_needs_no_choice(client_as, school, principal):
    user, only = _staff(school, "دورٌ واحد")

    _depart_post(client_as(principal), user)

    only.refresh_from_db()
    assert only.is_active is False


def test_the_profile_asks_which_role_only_when_there_are_several(client_as, school, principal):
    multi, _, _ = _two_roles(school)
    single, _ = _staff(school, "واحد")
    client = client_as(principal)

    multi_page = client.get(reverse("staff_affairs:staff_profile", args=[multi.pk]))
    single_page = client.get(reverse("staff_affairs:staff_profile", args=[single.pk]))

    assert b'name="membership"' in multi_page.content
    assert b'name="membership"' not in single_page.content
