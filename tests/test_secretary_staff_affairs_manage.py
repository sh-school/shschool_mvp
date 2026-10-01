"""السكرتيرُ وصلاحيّةُ `STAFF_AFFAIRS_MANAGE` — W-20261001-026.

قرارُ المالك: يُمنح السكرتيرُ هذه الصلاحيّةَ كاملةً (ملفُّ الموظّف، إجازاتُه، بياناتُه
الشخصيّة) إضافةً لصلاحيّاته الثلاث السابقة. كان مُستثنًى صراحةً (`core/permissions.py`،
المراجعةُ الرجعيّةُ W-20261001-006) فيردّه الحارسُ 403 عن هذه الشاشات.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from core import permissions as perm
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def secretary_user(school):
    role = RoleFactory(school=school, name="secretary")
    user = UserFactory(full_name="سكرتيرةُ المدرسة")
    MembershipFactory(user=user, school=school, role=role)
    return user


class TestSecretaryIsInStaffAffairsManage:
    def test_secretary_is_in_the_frozenset(self):
        assert "secretary" in perm.STAFF_AFFAIRS_MANAGE

    def test_existing_roles_are_kept(self):
        for role in ("principal", "vice_admin", "vice_academic", "platform_developer"):
            assert role in perm.STAFF_AFFAIRS_MANAGE


class TestSecretaryReachesStaffAffairs:
    """الوصولُ الفعليُّ عبر الشاشات — لا الفرضُ فقط."""

    def test_secretary_opens_the_dashboard(self, client_as, secretary_user):
        response = client_as(secretary_user).get(reverse("staff_affairs:dashboard"))
        assert response.status_code == 200

    def test_secretary_opens_the_staff_list(self, client_as, secretary_user):
        response = client_as(secretary_user).get(reverse("staff_affairs:staff_list"))
        assert response.status_code == 200

    def test_secretary_opens_a_staff_profile(self, client_as, secretary_user, school):
        role = RoleFactory(school=school, name="teacher")
        teacher = UserFactory(full_name="معلّمٌ اصطناعيّ", employee_number="T-9001")
        MembershipFactory(user=teacher, school=school, role=role)

        response = client_as(secretary_user).get(
            reverse("staff_affairs:staff_profile", kwargs={"user_id": teacher.id})
        )
        assert response.status_code == 200

    def test_secretary_opens_leave_requests(self, client_as, secretary_user):
        response = client_as(secretary_user).get(reverse("staff_affairs:leave_list"))
        assert response.status_code == 200
