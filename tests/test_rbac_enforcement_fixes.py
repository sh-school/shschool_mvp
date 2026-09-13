"""حرّاسُ إصلاحات الفرض — كلُّ اختبارٍ هنا كان عيباً مقيساً قبل أن يصير اختباراً.

المرجع: `docs/rbac_role_authority_study_2026-09.md` §٠٩ (ثغراتُ الفرض).
"""

import logging

import pytest
from django.urls import reverse

from tests.conftest import MembershipFactory, RoleFactory, UserFactory


@pytest.fixture
def transport_officer_user(db, school):
    """مسؤولُ النقل — إداريُّ المنظومة، لا مرافقُ الحافلة."""
    role = RoleFactory(school=school, name="transport_officer")
    user = UserFactory(full_name="مسؤول النقل")
    MembershipFactory(user=user, school=school, role=role)
    return user


class TestTransportOfficerReachesTransport:
    """`TRANSPORT_FULL` تمنحه الوحدة، والوحدةُ المسجّلةُ تسمح له — والحارسُ كان يردّه."""

    def test_transport_officer_can_open_transport(self, client_as, transport_officer_user):
        response = client_as(transport_officer_user).get(reverse("transport:dashboard"))
        assert response.status_code == 200, "مسؤولُ النقل محجوبٌ عن وحدةِ النقل"

    def test_bus_supervisor_still_allowed(self, client_as, bus_supervisor_user):
        assert client_as(bus_supervisor_user).get(reverse("transport:dashboard")).status_code == 200

    def test_teacher_still_denied(self, client_as, teacher_user):
        assert client_as(teacher_user).get(reverse("transport:dashboard")).status_code == 403


class TestHasAnyRoleReadsMemberships:
    """الدالّةُ تَعِد بفحص الأدوار كلِّها — وكانت تفحص الدورَ الحاكمَ وحدَه."""

    def test_staff_who_is_also_parent_is_seen_as_parent(self, school, teacher_user):
        parent_role = RoleFactory(school=school, name="parent")
        MembershipFactory(user=teacher_user, school=school, role=parent_role)
        teacher_user.invalidate_active_membership()

        assert teacher_user.get_role() == "teacher", "الكادرُ يبقى الدورَ الحاكم"
        assert teacher_user.has_any_role("parent"), "عضويّةُ وليِّ الأمر نشطةٌ ولا تُرى"
        assert teacher_user.has_any_role("teacher")

    def test_absent_role_is_false(self, teacher_user):
        assert not teacher_user.has_any_role("principal", "nurse")

    def test_inactive_membership_does_not_count(self, teacher_user):
        teacher_user.memberships.update(is_active=False)
        assert not teacher_user.has_any_role("teacher")


class TestApiTeacherPermissionExpandsInheritance:
    """من يرث المعلّمَ يراه الويبُ ولا يراه الـAPI — حتّى هذا الإصلاح."""

    def test_inheriting_roles_are_included(self):
        from api.permissions import _TEACHER_API_ROLES

        for role in ("teacher", "coordinator", "ese_teacher", "teacher_assistant"):
            assert role in _TEACHER_API_ROLES, f"{role} محجوبٌ عن نقاط المعلّم"

    def test_academic_leadership_in_administrative_out(self):
        """المديرُ والنائبُ الأكاديميُّ يرثان المعلّم — والنائبُ الإداريُّ لا يرثه."""
        from api.permissions import _TEACHER_API_ROLES

        assert {"principal", "vice_academic"} <= _TEACHER_API_ROLES
        assert "vice_admin" not in _TEACHER_API_ROLES, "«كلٌّ في تخصّصه» — نقاطٌ تدريسيّة"

    def test_beneficiaries_stay_out(self):
        from api.permissions import _TEACHER_API_ROLES

        assert "student" not in _TEACHER_API_ROLES
        assert "parent" not in _TEACHER_API_ROLES


class TestSameDepartmentFailsClosed:
    """حارسٌ يمرّر عند غياب القسم ليس حارساً."""

    def test_missing_department_is_denied(self, rf, teacher_user):
        from api.permissions import IsSameDepartment

        request = rf.get("/api/v1/anything/")
        request.user = teacher_user

        class _View:
            kwargs = {}

        assert IsSameDepartment().has_permission(request, _View()) is False


class TestDenialsAreLogged:
    """الرفضُ الصامتُ لا يُقاس — ولا يُعرف من سيُحجَب قبل أن يُحجَب."""

    def test_http_denial_writes_a_line(self, client_as, teacher_user, caplog):
        """طلبٌ حقيقيٌّ يُردّ — والميدلوير يسبق الديكوريتور حين يكون للوحدة مسارٌ مسجَّل."""
        with caplog.at_level(logging.WARNING, logger="core.permissions"):
            client_as(teacher_user).get(reverse("transport:dashboard"))

        denials = [r for r in caplog.records if "access_denied" in r.getMessage()]
        assert denials, "الـ403 خرجت بلا سطرٍ في السجلّ"
        message = denials[0].getMessage()
        assert "role=teacher" in message
        assert "path=/transport/" in message

    def test_decorator_denial_writes_a_line(self, rf, teacher_user, caplog):
        """والديكوريتورُ نفسُه يكتب — وهو الطبقةُ الوحيدةُ في المسارات غير المسجَّلة."""
        from core.permissions import role_required

        @role_required("principal")
        def _view(request):  # pragma: no cover - لا يُنفَّذ، الحارسُ يردّ قبله
            raise AssertionError("مرّ من حارسٍ لا يسمح له")

        request = rf.get("/teacher/schedule/")
        request.user = teacher_user

        with caplog.at_level(logging.WARNING, logger="core.permissions"):
            response = _view(request)

        assert response.status_code == 403
        message = next(r.getMessage() for r in caplog.records if "access_denied" in r.getMessage())
        assert "source=decorator" in message
        assert "role=teacher" in message

    def test_log_carries_no_personal_identifier(self, client_as, teacher_user, caplog):
        with caplog.at_level(logging.WARNING, logger="core.permissions"):
            client_as(teacher_user).get(reverse("transport:dashboard"))

        for record in caplog.records:
            message = record.getMessage()
            assert teacher_user.national_id not in message, "رقمٌ شخصيٌّ في السجلّ (PDPPL)"
            assert teacher_user.full_name not in message


class TestSupportCompanionIsItsOwnRole:
    """مرافقُ الدعم ليس مساعدَ معلّم — والتفريقُ منصوصٌ في سياسة الدعم الإضافيّ."""

    def test_title_maps_to_its_own_role(self):
        from core.management.commands.import_staff_register import role_for

        assert role_for("مرافق الدعم") == "support_companion"

    def test_it_is_not_mapped_to_ese_assistant(self):
        from core.management.commands.import_staff_register import role_for

        assert role_for("مرافق الدعم") != "ese_assistant", "الدمجُ يفتح له شاشاتِ مساعدِ معلّم"

    def test_it_is_staff_and_tier_four(self, db, school):
        from core.models.access import ALL_STAFF_ROLES

        assert "support_companion" in ALL_STAFF_ROLES
        role = RoleFactory(school=school, name="support_companion")
        assert role.tier == 4
        assert role.is_staff_role

    def test_it_inherits_nothing_from_teaching(self):
        """الوراثةُ تمنح صلاحيّاتٍ تدريسيّة — ومرافقُ الدعم ليس تربويّاً بنصّ المصدر."""
        from core.permissions import expand_roles

        assert "support_companion" not in expand_roles({"teacher"})
        assert "support_companion" not in expand_roles({"ese_teacher"})

    def test_it_reaches_a_dashboard(self):
        """يدخل فلا يجد شاشةً فارغة — وإن لم تُبنَ بعدُ وحدةُ سجلّ الرعاية."""
        from core.permissions import DASHBOARD_ROLES

        assert "support_companion" in DASHBOARD_ROLES

    def test_its_arabic_label_is_the_ministry_title(self, db, school):
        role = RoleFactory(school=school, name="support_companion")
        assert role.get_name_display() == "مرافق الدعم"
