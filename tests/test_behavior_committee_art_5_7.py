"""لجنةُ الانضباط تطابق م5.7 — W-20261001-023.

م5.7 من سياسة إدارة سلوك الطلبة (08_conduct_policy_2026.md): «الأعضاء الأساسيون: مدير المدرسة، نائب
المدير للشؤون الإدارية وشؤون الطلاب، نائب المدير للشؤون الأكاديمية، منسق شؤون الطلبة، الاختصاصي
الاجتماعي، الاختصاصي النفسي، المشرف الإداري». كانت القائمتان (`BEHAVIOR_COMMITTEE` و`COMMITTEE_ROLES`)
تُسقطان المشرفَ الإداريّ والاختصاصيَّ النفسيّ، وتكرّران القائمةَ بدل مصدرٍ واحد.
"""

import pytest

from behavior.committee_services import eligible_member_ids
from behavior.services import BehaviorPermissions
from core.capabilities import has_capability
from core.permissions import BEHAVIOR_COMMITTEE, BEHAVIOR_COMMITTEE_ART_5_7
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

#: نصُّ م5.7 بأسماء الأدوار في المنصّة — الاختصاصي الاجتماعي (social_worker) والنفسي (psychologist).
ART_5_7 = {
    "principal",  # مدير المدرسة
    "vice_admin",  # نائب المدير للشؤون الإدارية وشؤون الطلاب
    "vice_academic",  # نائب المدير للشؤون الأكاديمية
    "student_affairs_coordinator",  # منسق شؤون الطلبة
    "social_worker",  # الاختصاصي الاجتماعي
    "psychologist",  # الاختصاصي النفسي
    "admin_supervisor",  # المشرف الإداري
}


def _user_with(school, role_name):
    user = UserFactory(full_name=f"مستخدم {role_name}")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role_name))
    return user


def test_the_committee_is_exactly_the_core_members_of_article_5_7():
    assert BEHAVIOR_COMMITTEE_ART_5_7 == ART_5_7


def test_the_legacy_specialist_stays_one_release_and_nobody_else_joins():
    assert BEHAVIOR_COMMITTEE - BEHAVIOR_COMMITTEE_ART_5_7 == {"specialist"}


def test_the_service_reads_the_same_set_not_a_copy():
    assert BehaviorPermissions.COMMITTEE_ROLES is BEHAVIOR_COMMITTEE


@pytest.mark.django_db
@pytest.mark.parametrize("role", sorted(ART_5_7))
def test_each_article_member_holds_the_committee_capability(school, role):
    user = _user_with(school, role)
    assert has_capability(user, "behavior.committee")
    assert BehaviorPermissions.is_committee(user)


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["teacher", "coordinator", "nurse", "activities_coordinator"])
def test_the_rest_do_not_join(school, role):
    """م5.7: «المعلم ليس عضواً في اللجنة» — ولا غيرُ المذكورين."""
    assert not BehaviorPermissions.is_committee(_user_with(school, role))


@pytest.mark.django_db
def test_the_voting_quorum_counts_the_new_members(school):
    """النصابُ يُحسب من المؤهَّلين: دخولُ المشرف الإداريّ والنفسيّ يرفعه."""
    users = [_user_with(school, role) for role in ("principal", "admin_supervisor", "psychologist")]
    assert eligible_member_ids(school) == {user.id for user in users}
