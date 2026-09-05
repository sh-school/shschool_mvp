"""دورُ «منسّق المشاريع الإلكترونية» — المسمّى الوزاريّ لا الحلُّ المؤقّت.

Electronic Projects Coordinator مسمّىً رسميٌّ في وزارة التعليم القطريّة تتابعه
إدارةُ التعليم الإلكترونيّ. ولم يكن في مفردات المنصّة، فسُجّل شاغلُه «منسّقاً
أكاديمياً بلا قسم» — دورٌ يحمل دلالةَ القسم في الصلاحيات والإحصاءات. صار له
دورُه: يرث المعلّم (فقد يحمل حصصاً بنصابٍ مخفَّض)، وهو في طبقة المنسّقين.
"""

import pytest
from django.urls import reverse

from core.models import Role
from core.permissions import (
    ALL_STAFF_ROLES,
    ATTENDANCE_RECORD,
    OBSERVATION_SELF_CREATE,
    SCHEDULE_VIEW,
    TIER_3_SUPERVISORS,
    expand_roles,
)

ROLE = "e_projects_coordinator"


@pytest.mark.django_db
class TestVocabulary:
    def test_the_role_exists_with_the_ministry_title(self):
        names = dict(Role.ROLES)
        assert names[ROLE] == "منسق المشاريع الإلكترونية"

    def test_it_sits_with_the_coordinators(self, school):
        role = Role.objects.create(school=school, name=ROLE)
        assert role.tier == 3
        assert ROLE in TIER_3_SUPERVISORS
        assert ROLE in ALL_STAFF_ROLES

    def test_the_membership_resolves_to_the_role(self, e_projects_coordinator_user):
        assert e_projects_coordinator_user.get_role() == ROLE


class TestPermissions:
    def test_it_inherits_the_teacher(self):
        """ما يُمنح للمعلّم يُمنح له — فقد يحمل حصصاً."""
        assert ROLE in expand_roles({"teacher"})

    def test_it_is_not_an_academic_coordinator(self):
        """لا يرث المنسّق: لا اعتمادَ تبديلٍ ولا نطاقَ قسم."""
        assert ROLE not in expand_roles({"coordinator"})

    def test_it_sees_the_schedule_records_attendance_and_self_assesses(self):
        assert ROLE in SCHEDULE_VIEW
        assert ROLE in ATTENDANCE_RECORD
        assert ROLE in OBSERVATION_SELF_CREATE


@pytest.mark.django_db
class TestModules:
    @pytest.mark.parametrize(
        "module",
        [
            "schedule",
            "attendance",
            "quality",
            "quality_evaluations",
            "reports",
            "notifications",
            "library",
            "behavior",
        ],
    )
    def test_the_middleware_lets_it_into_the_staff_modules(self, module):
        from core.module_registry import get_module

        mod = get_module(module)
        assert mod is not None, module
        assert ROLE in mod.allowed_roles, module

    def test_the_dashboard_opens_as_a_teacher_dashboard(self, client, e_projects_coordinator_user):
        client.force_login(e_projects_coordinator_user)
        response = client.get(reverse("dashboard"))
        assert response.status_code == 200

    def test_the_seed_creates_it_for_every_school(self, school):
        from django.core.management import call_command

        call_command("seed_new_roles", verbosity=0)
        assert Role.objects.filter(school=school, name=ROLE).exists()
        call_command("seed_new_roles", verbosity=0)
        assert Role.objects.filter(school=school, name=ROLE).count() == 1
