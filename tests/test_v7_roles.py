"""
tests/test_v7_roles.py
Tests for the 7 new v7 roles (MOE Cabinet Decision 32/2019)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Role creation & membership
2. Permission sets (ALL_STAFF_ROLES, DASHBOARD_ROLES, etc.)
3. Tier classification
4. Module registry (middleware access)
5. Permission boundaries
"""

import pytest

from core.models import Role

# ══════════════════════════════════════════════════════════
#  1. ROLE & MEMBERSHIP — كل دور ينشأ ويعمل
# ══════════════════════════════════════════════════════════

V7_ROLES = [
    "activities_coordinator",
    "teacher_assistant",
    "ese_assistant",
    "speech_therapist",
    "occupational_therapist",
    "receptionist",
    "transport_officer",
]


@pytest.mark.django_db
class TestRoleCreation:
    """التأكد من أن كل دور v7 ينشأ بنجاح ويُعطي get_role() الصحيح."""

    @pytest.mark.parametrize("role_name", V7_ROLES)
    def test_role_exists_in_choices(self, role_name):
        valid_names = {c[0] for c in Role.ROLES}
        assert role_name in valid_names, f"{role_name} not in Role.ROLES choices"

    def test_activities_coordinator_role(self, activities_coordinator_user):
        assert activities_coordinator_user.get_role() == "activities_coordinator"

    def test_teacher_assistant_role(self, teacher_assistant_user):
        assert teacher_assistant_user.get_role() == "teacher_assistant"

    def test_ese_assistant_role(self, ese_assistant_user):
        assert ese_assistant_user.get_role() == "ese_assistant"

    def test_speech_therapist_role(self, speech_therapist_user):
        assert speech_therapist_user.get_role() == "speech_therapist"

    def test_occupational_therapist_role(self, occupational_therapist_user):
        assert occupational_therapist_user.get_role() == "occupational_therapist"

    def test_receptionist_role(self, receptionist_user):
        assert receptionist_user.get_role() == "receptionist"

    def test_transport_officer_role(self, transport_officer_user):
        assert transport_officer_user.get_role() == "transport_officer"


# ══════════════════════════════════════════════════════════
#  2. TIER CLASSIFICATION — كل دور في المستوى الصحيح
# ══════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestTierClassification:
    """التأكد من أن الأدوار v7 في المستوى الإداري الصحيح."""

    def test_activities_coordinator_tier3(self, school):
        role = Role.objects.create(school=school, name="activities_coordinator")
        assert role.tier == 3

    @pytest.mark.parametrize("role_name", [
        "teacher_assistant", "ese_assistant",
        "speech_therapist", "occupational_therapist",
        "receptionist", "transport_officer",
    ])
    def test_remaining_v7_are_tier4(self, school, role_name):
        role = Role.objects.create(school=school, name=role_name)
        assert role.tier == 4, f"{role_name} should be tier 4"


# ══════════════════════════════════════════════════════════
#  3. PERMISSION SETS — مجموعات الصلاحيات
# ══════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestPermissionSets:
    """التأكد من أن الأدوار v7 مدرجة في المجموعات الصحيحة."""

    def test_all_staff_roles_includes_v7(self):
        from core.permissions import ALL_STAFF_ROLES
        for r in V7_ROLES:
            assert r in ALL_STAFF_ROLES, f"{r} missing from ALL_STAFF_ROLES"

    def test_dashboard_roles_includes_assistants(self):
        from core.permissions import DASHBOARD_ROLES
        for r in ["teacher_assistant", "ese_assistant"]:
            assert r in DASHBOARD_ROLES, f"{r} missing from DASHBOARD_ROLES"

    def test_activities_coordinator_in_behavior_view_all(self):
        from core.permissions import BEHAVIOR_VIEW_ALL
        assert "activities_coordinator" in BEHAVIOR_VIEW_ALL

    def test_activities_coordinator_in_tier3(self):
        from core.permissions import TIER_3_SUPERVISORS
        assert "activities_coordinator" in TIER_3_SUPERVISORS


# ══════════════════════════════════════════════════════════
#  4. MODULE REGISTRY — middleware يسمح للأدوار v7
# ══════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestModuleRegistry:
    """التأكد من أن الأدوار v7 مسجّلة في الوحدات المناسبة."""

    def test_notifications_allows_all_v7(self):
        from core.module_registry import get_module
        mod = get_module("notifications")
        assert mod is not None
        for r in V7_ROLES:
            assert r in mod.allowed_roles, f"{r} missing from notifications allowed_roles"

    def test_transport_allows_transport_officer(self):
        from core.module_registry import get_module
        mod = get_module("transport")
        assert mod is not None
        assert "transport_officer" in mod.allowed_roles

    def test_behavior_allows_assistants(self):
        from core.module_registry import get_module
        mod = get_module("behavior")
        assert mod is not None
        for r in ["activities_coordinator", "teacher_assistant", "ese_assistant"]:
            assert r in mod.allowed_roles, f"{r} missing from behavior allowed_roles"

    def test_quality_evaluations_allows_all_v7(self):
        from core.module_registry import get_module
        mod = get_module("quality_evaluations")
        assert mod is not None
        for r in V7_ROLES:
            assert r in mod.allowed_roles, f"{r} missing from quality_evaluations"

    def test_schedule_allows_teaching_v7(self):
        from core.module_registry import get_module
        mod = get_module("schedule")
        assert mod is not None
        for r in ["teacher_assistant", "ese_assistant", "speech_therapist", "occupational_therapist"]:
            assert r in mod.allowed_roles, f"{r} missing from schedule"

    def test_assessments_allows_assistants(self):
        from core.module_registry import get_module
        mod = get_module("assessments")
        assert mod is not None
        for r in ["teacher_assistant", "ese_assistant"]:
            assert r in mod.allowed_roles, f"{r} missing from assessments"


# ══════════════════════════════════════════════════════════
#  5. PERMISSION BOUNDARIES — الأدوار v7 لا تصل للقيادة
# ══════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestPermissionBoundaries:
    """الأدوار v7 يجب أن لا تكون في مجموعات القيادة."""

    def test_v7_not_in_leadership(self):
        from core.permissions import LEADERSHIP
        for r in V7_ROLES:
            assert r not in LEADERSHIP, f"{r} should NOT be in LEADERSHIP"

    def test_v7_not_in_staging(self):
        from core.module_registry import get_module
        mod = get_module("staging")
        if mod:
            for r in V7_ROLES:
                assert r not in mod.allowed_roles, f"{r} should NOT be in staging"

    def test_v7_not_in_breach(self):
        from core.module_registry import get_module
        mod = get_module("breach")
        if mod:
            for r in V7_ROLES:
                assert r not in mod.allowed_roles, f"{r} should NOT be in breach"

    def test_transport_officer_not_in_analytics(self):
        from core.module_registry import get_module
        mod = get_module("analytics")
        if mod:
            assert "transport_officer" not in mod.allowed_roles

    def test_receptionist_not_in_analytics(self):
        from core.module_registry import get_module
        mod = get_module("analytics")
        if mod:
            assert "receptionist" not in mod.allowed_roles


# ══════════════════════════════════════════════════════════
#  6. DASHBOARD ACCESS — HTTP level
# ══════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestDashboardAccess:
    """كل دور v7 يحصل على 200 من /dashboard/."""

    def test_teacher_assistant_dashboard(self, client_as, teacher_assistant_user):
        c = client_as(teacher_assistant_user)
        resp = c.get("/dashboard/")
        assert resp.status_code == 200

    def test_ese_assistant_dashboard(self, client_as, ese_assistant_user):
        c = client_as(ese_assistant_user)
        resp = c.get("/dashboard/")
        assert resp.status_code == 200

    def test_speech_therapist_dashboard(self, client_as, speech_therapist_user):
        c = client_as(speech_therapist_user)
        resp = c.get("/dashboard/")
        assert resp.status_code == 200

    def test_occupational_therapist_dashboard(self, client_as, occupational_therapist_user):
        c = client_as(occupational_therapist_user)
        resp = c.get("/dashboard/")
        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════
#  7. REGRESSION — الأدوار القديمة لم تتأثر
# ══════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestExistingRolesRegression:
    """التأكد من أن الأدوار الموجودة مسبقاً لم تتأثر."""

    def test_principal_dashboard(self, client_as, principal_user):
        c = client_as(principal_user)
        resp = c.get("/dashboard/")
        assert resp.status_code == 200

    def test_teacher_dashboard(self, client_as, teacher_user):
        c = client_as(teacher_user)
        resp = c.get("/dashboard/")
        assert resp.status_code == 200

    def test_coordinator_dashboard(self, client_as, coordinator_user):
        c = client_as(coordinator_user)
        resp = c.get("/dashboard/")
        assert resp.status_code == 200

    def test_student_dashboard(self, client_as, student_user):
        c = client_as(student_user)
        resp = c.get("/dashboard/")
        assert resp.status_code == 200
