"""لجنةُ الانضباط تطابق م5.7 — W-20261001-023.

م5.7 من سياسة إدارة سلوك الطلبة (08_conduct_policy_2026.md): «الأعضاء الأساسيون: مدير المدرسة، نائب
المدير للشؤون الإدارية وشؤون الطلاب، نائب المدير للشؤون الأكاديمية، منسق شؤون الطلبة، الاختصاصي
الاجتماعي، الاختصاصي النفسي، المشرف الإداري». كانت القائمتان (`BEHAVIOR_COMMITTEE` و`COMMITTEE_ROLES`)
تُسقطان المشرفَ الإداريّ والاختصاصيَّ النفسيّ، وتكرّران القائمةَ بدل مصدرٍ واحد.
"""

import pytest
from django.urls import reverse

from behavior.committee_services import eligible_member_ids, may_act_on
from behavior.services import BehaviorPermissions
from core.capabilities import has_capability
from core.permissions import (
    BEHAVIOR_COMMITTEE,
    BEHAVIOR_COMMITTEE_ART_5_7,
    BEHAVIOR_COMMITTEE_CASE_SCOPED,
)
from tests.conftest import (
    BehaviorInfractionFactory,
    MembershipFactory,
    RoleFactory,
    UserFactory,
)
from tests.test_period_register import klass, supervisor, teacher, year  # noqa: F401
from tests.test_supervisor_behavior_scope import far_klass, mine, principal, theirs  # noqa: F401

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


def test_the_supervisor_is_case_scoped_not_school_wide():
    assert BEHAVIOR_COMMITTEE_CASE_SCOPED == {"admin_supervisor"}


@pytest.mark.django_db
class TestOneSupervisorPerCase:
    """قرارُ المالك 2026-10-05: يدخل اللجنةَ مشرفُ جناح الطالب المعنيّ وحدَه — واحدٌ لكلّ قضيّة."""

    def _case(self, school, student, reporter, level=3):
        return BehaviorInfractionFactory(
            school=school, student=student, reported_by=reporter, level=level
        )

    def test_the_wing_supervisor_votes_in_his_wings_case_only(
        self, school, seeded_calendar, mine, theirs, supervisor, teacher, principal
    ):
        near = self._case(school, mine, teacher)
        far = self._case(school, theirs, teacher)
        assert supervisor.pk in eligible_member_ids(school, near)
        assert supervisor.pk not in eligible_member_ids(school, far)

    def test_other_supervisors_do_not_vote_at_all(
        self, school, seeded_calendar, mine, supervisor, teacher
    ):
        other = _user_with(school, "admin_supervisor")
        case = self._case(school, mine, teacher)
        members = eligible_member_ids(school, case)
        assert supervisor.pk in members
        assert other.pk not in members

    def test_the_quorum_grows_by_one_not_by_every_supervisor(
        self, school, seeded_calendar, mine, supervisor, teacher
    ):
        for _ in range(4):
            _user_with(school, "admin_supervisor")  # أربعةٌ آخرون بلا جناح الطالب
        fixed = [_user_with(school, role) for role in ("principal", "vice_admin", "psychologist")]
        case = self._case(school, mine, teacher)
        assert eligible_member_ids(school, case) == {u.pk for u in fixed} | {supervisor.pk}
        assert eligible_member_ids(school) == {u.pk for u in fixed}

    def test_the_reporter_does_not_vote_even_if_he_is_the_wing_supervisor(
        self, school, seeded_calendar, mine, supervisor
    ):
        case = self._case(school, mine, supervisor)
        assert supervisor.pk not in eligible_member_ids(school, case)

    def test_may_act_on_follows_the_wing(
        self, school, seeded_calendar, mine, theirs, supervisor, teacher, principal
    ):
        near = self._case(school, mine, teacher)
        far = self._case(school, theirs, teacher)
        assert may_act_on(supervisor, near)
        assert not may_act_on(supervisor, far)
        assert may_act_on(principal, near) and may_act_on(principal, far)


@pytest.mark.django_db
class TestTheScreens:
    def test_the_dashboard_lists_only_the_wings_cases_for_the_supervisor(
        self, client_as, school, seeded_calendar, mine, theirs, supervisor, teacher
    ):
        near = BehaviorInfractionFactory(school=school, student=mine, reported_by=teacher, level=3)
        BehaviorInfractionFactory(school=school, student=theirs, reported_by=teacher, level=3)
        ctx = client_as(supervisor).get(reverse("behavior:committee")).context
        assert [c.pk for c in ctx["open_cases"]] == [near.pk]
        assert ctx["stats"]["open_count"] == 1

    def test_the_principal_still_sees_the_whole_school(
        self, client_as, school, seeded_calendar, mine, theirs, principal, teacher
    ):
        for student in (mine, theirs):
            BehaviorInfractionFactory(school=school, student=student, reported_by=teacher, level=3)
        ctx = client_as(principal).get(reverse("behavior:committee")).context
        assert ctx["stats"]["open_count"] == 2

    def test_a_case_of_another_wing_is_404_for_the_supervisor(
        self, client_as, school, seeded_calendar, theirs, supervisor, teacher
    ):
        far = BehaviorInfractionFactory(school=school, student=theirs, reported_by=teacher, level=3)
        response = client_as(supervisor).get(reverse("behavior:committee_decision", args=[far.pk]))
        assert response.status_code == 404
