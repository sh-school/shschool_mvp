"""
E2E Test Fixtures — SchoolOS v5.1.1
════════════════════════════════════
Playwright fixtures لاختبارات المتصفح الشاملة.
يستخدم pytest-playwright + Django live_server.
"""

import pytest

from core.models import CustomUser, School, Role, Membership, ClassGroup, StudentEnrollment


# ── School + Roles Setup ────────────────────────────────────────

@pytest.fixture
def e2e_school(db):
    """مدرسة اختبار E2E مع جميع الأدوار."""
    school = School.objects.create(name="مدرسة اختبار E2E", code="E2E01")
    return school


@pytest.fixture
def e2e_roles(e2e_school):
    """إنشاء جميع الأدوار للمدرسة."""
    roles = {}
    for name in [
        "principal", "vice_admin", "vice_academic", "coordinator",
        "teacher", "specialist", "nurse", "librarian",
        "bus_supervisor", "admin", "student", "parent",
    ]:
        roles[name] = Role.objects.create(school=e2e_school, name=name)
    return roles


def _make_user(school, role_obj, national_id, name, password="TestPass123!"):
    """Helper: إنشاء مستخدم مع عضوية."""
    user = CustomUser.objects.create_user(
        national_id=national_id,
        full_name=name,
        password=password,
    )
    user.must_change_password = False
    user.save(update_fields=["must_change_password"])
    Membership.objects.create(user=user, school=school, role=role_obj)
    return user


@pytest.fixture
def e2e_principal(e2e_school, e2e_roles):
    return _make_user(e2e_school, e2e_roles["principal"], "99900000001", "مدير الاختبار")


@pytest.fixture
def e2e_teacher(e2e_school, e2e_roles):
    return _make_user(e2e_school, e2e_roles["teacher"], "99900000002", "معلم الاختبار")


@pytest.fixture
def e2e_student(e2e_school, e2e_roles):
    return _make_user(e2e_school, e2e_roles["student"], "99900000003", "طالب الاختبار")


# ── Login Helpers ────────────────────────────────────────────────

@pytest.fixture
def login(page, live_server):
    """Factory fixture: تسجيل دخول مستخدم في المتصفح."""

    def _login(user, password="TestPass123!"):
        page.goto(f"{live_server.url}/auth/login/")
        page.fill('input[name="national_id"]', user.national_id)
        page.fill('input[name="password"]', password)
        page.click('button[type="submit"]')
        page.wait_for_url("**/dashboard/**", timeout=10000)
        return page

    return _login


@pytest.fixture
def principal_page(login, e2e_principal):
    """صفحة مسجّل دخولها كمدير."""
    return login(e2e_principal)


@pytest.fixture
def teacher_page(login, e2e_teacher):
    """صفحة مسجّل دخولها كمعلم."""
    return login(e2e_teacher)
