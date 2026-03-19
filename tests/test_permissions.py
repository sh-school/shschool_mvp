"""
tests/test_permissions.py
اختبارات نظام الصلاحيات (RBAC)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
يختبر: كل ديكوريتر، منع الوصول، السماح للأدوار الصحيحة
"""
import pytest
from django.urls import reverse


# ══════════════════════════════════════════════
#  مساعد — التحقق من الاستجابة
# ══════════════════════════════════════════════

def assert_allowed(response):
    """الصفحة مسموح بها — 200 أو redirect داخلي"""
    assert response.status_code in (200, 302), \
        f"Expected 200/302, got {response.status_code}"

def assert_forbidden(response):
    """الصفحة محجوبة — 403"""
    assert response.status_code == 403, \
        f"Expected 403, got {response.status_code}"

def assert_redirect_to_login(response):
    """غير مسجل — يُعاد توجيهه لصفحة الدخول"""
    assert response.status_code == 302
    assert "login" in response["Location"] or "auth" in response["Location"]


# ══════════════════════════════════════════════
#  اختبارات الوصول للعيادة (nurse_required)
# ══════════════════════════════════════════════

@pytest.mark.django_db
class TestClinicPermissions:

    def test_nurse_can_access_clinic(self, client_as, nurse_user):
        client = client_as(nurse_user)
        response = client.get("/clinic/")
        assert_allowed(response)

    def test_principal_can_access_clinic(self, client_as, principal_user):
        client = client_as(principal_user)
        response = client.get("/clinic/")
        assert_allowed(response)

    def test_teacher_cannot_access_clinic(self, client_as, teacher_user):
        client = client_as(teacher_user)
        response = client.get("/clinic/")
        assert_forbidden(response)

    def test_student_cannot_access_clinic(self, client_as, student_user):
        client = client_as(student_user)
        response = client.get("/clinic/")
        assert_forbidden(response)

    def test_unauthenticated_redirected(self, client):
        response = client.get("/clinic/")
        assert_redirect_to_login(response)


# ══════════════════════════════════════════════
#  اختبارات الوصول للنقل (bus_supervisor_required)
# ══════════════════════════════════════════════

@pytest.mark.django_db
class TestTransportPermissions:

    def test_bus_supervisor_can_access(self, client_as, bus_supervisor_user):
        client = client_as(bus_supervisor_user)
        response = client.get("/transport/")
        assert_allowed(response)

    def test_principal_can_access_transport(self, client_as, principal_user):
        client = client_as(principal_user)
        response = client.get("/transport/")
        assert_allowed(response)

    def test_teacher_cannot_access_transport(self, client_as, teacher_user):
        client = client_as(teacher_user)
        response = client.get("/transport/")
        assert_forbidden(response)

    def test_nurse_cannot_access_transport(self, client_as, nurse_user):
        client = client_as(nurse_user)
        response = client.get("/transport/")
        assert_forbidden(response)

    def test_unauthenticated_redirected(self, client):
        response = client.get("/transport/")
        assert_redirect_to_login(response)


# ══════════════════════════════════════════════
#  اختبارات الوصول للمكتبة (librarian_required/staff_required)
# ══════════════════════════════════════════════

@pytest.mark.django_db
class TestLibraryPermissions:

    def test_librarian_can_access_dashboard(self, client_as, librarian_user):
        client = client_as(librarian_user)
        response = client.get("/library/dashboard/")
        assert_allowed(response)

    def test_teacher_can_view_books(self, client_as, teacher_user):
        """staff_required — المعلم يمكنه رؤية الكتب"""
        client = client_as(teacher_user)
        response = client.get("/library/books/")
        assert_allowed(response)

    def test_teacher_cannot_borrow_directly(self, client_as, teacher_user):
        """librarian_required — المعلم لا يستطيع إعارة"""
        client = client_as(teacher_user)
        response = client.get("/library/borrow/")
        assert_forbidden(response)

    def test_librarian_can_borrow(self, client_as, librarian_user):
        client = client_as(librarian_user)
        response = client.get("/library/borrow/")
        assert_allowed(response)

    def test_parent_cannot_access_library_dashboard(self, client_as, parent_user):
        client = client_as(parent_user)
        response = client.get("/library/dashboard/")
        assert_forbidden(response)


# ══════════════════════════════════════════════
#  اختبارات السلوك (role-based)
# ══════════════════════════════════════════════

@pytest.mark.django_db
class TestBehaviorPermissions:

    def test_teacher_can_access_behavior_dashboard(self, client_as, teacher_user):
        client = client_as(teacher_user)
        response = client.get("/behavior/dashboard/")
        assert_allowed(response)

    def test_teacher_can_report_infraction(self, client_as, teacher_user):
        client = client_as(teacher_user)
        response = client.get("/behavior/report/")
        assert_allowed(response)

    def test_teacher_cannot_access_committee(self, client_as, teacher_user):
        """لجنة الضبط — للمدير والنواب فقط"""
        client = client_as(teacher_user)
        response = client.get("/behavior/committee/")
        assert_forbidden(response)

    def test_principal_can_access_committee(self, client_as, principal_user):
        client = client_as(principal_user)
        response = client.get("/behavior/committee/")
        assert_allowed(response)

    def test_specialist_can_access_committee(self, client_as, specialist_user):
        client = client_as(specialist_user)
        response = client.get("/behavior/committee/")
        assert_allowed(response)

    def test_parent_cannot_access_behavior(self, client_as, parent_user):
        client = client_as(parent_user)
        response = client.get("/behavior/dashboard/")
        assert_forbidden(response)

    def test_student_cannot_access_behavior(self, client_as, student_user):
        client = client_as(student_user)
        response = client.get("/behavior/dashboard/")
        assert_forbidden(response)


# ══════════════════════════════════════════════
#  اختبارات Analytics (admin only)
# ══════════════════════════════════════════════

@pytest.mark.django_db
class TestAnalyticsPermissions:

    def test_principal_can_access_analytics(self, client_as, principal_user):
        client = client_as(principal_user)
        response = client.get("/analytics/")
        assert_allowed(response)

    def test_teacher_cannot_access_analytics(self, client_as, teacher_user):
        client = client_as(teacher_user)
        response = client.get("/analytics/")
        assert response.status_code == 403

    def test_nurse_cannot_access_analytics(self, client_as, nurse_user):
        client = client_as(nurse_user)
        response = client.get("/analytics/")
        assert response.status_code == 403


# ══════════════════════════════════════════════
#  اختبار الأدوار المزدوجة (موظف-ولي أمر)
# ══════════════════════════════════════════════

@pytest.mark.django_db
class TestDualRole:

    def test_employee_parent_has_two_memberships(self, db, school):
        from .conftest import UserFactory, RoleFactory, MembershipFactory
        teacher_role = RoleFactory(school=school, name="teacher")
        parent_role  = RoleFactory(school=school, name="parent")
        user = UserFactory()
        MembershipFactory(user=user, school=school, role=teacher_role)
        MembershipFactory(user=user, school=school, role=parent_role)
        count = user.memberships.filter(school=school, is_active=True).count()
        assert count == 2

    def test_get_role_returns_first_active(self, db, school):
        """get_role() يُعيد الدور الأول النشط"""
        from .conftest import UserFactory, RoleFactory, MembershipFactory
        teacher_role = RoleFactory(school=school, name="teacher")
        user = UserFactory()
        MembershipFactory(user=user, school=school, role=teacher_role)
        assert user.get_role() in ("teacher", "parent", "principal")  # أي دور صحيح
