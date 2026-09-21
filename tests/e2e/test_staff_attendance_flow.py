"""
E2E: حضورُ الموظّفين والأذونات والتكليفات — بمتصفّحٍ حقيقيّ.
════════════════════════════════════════════════════════
اختباراتُ الخدمة والعروض تغطّي القواعد؛ وهذه تغطّي ما لا تراه: أنّ الشاشاتِ تُفتح فعلاً
بعد تسجيل دخولٍ حقيقيّ، وأنّ التكليفَ يُكتب من النموذج نفسِه وتظهر نتيجتُه، وأنّ من لا دورَ له
لا يفتح الشاشة. (مواصفة الحضور: docs/compliance/staff_attendance_spec.md، ق-3.)
"""

import pytest

pytest.importorskip("pytest_playwright")
from playwright.sync_api import expect  # noqa: E402

from core.models import Role  # noqa: E402
from tests.e2e.conftest import _make_user  # noqa: E402

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def e2e_deputy(e2e_school, e2e_roles):
    """نائبُ الشؤون الإدارية — يُكلَّف بأعباء المدير."""
    return _make_user(e2e_school, e2e_roles["vice_admin"], "99900000011", "نائب الاختبار")


@pytest.fixture
def e2e_secretary(e2e_school):
    role = Role.objects.create(school=e2e_school, name="secretary")
    return _make_user(e2e_school, role, "99900000012", "سكرتير الاختبار")


@pytest.fixture
def secretary_page(login, e2e_secretary):
    return login(e2e_secretary)


class TestAssignmentsScreen:
    def test_the_principal_tasks_a_deputy_and_sees_it_listed(
        self, principal_page, live_server, e2e_deputy
    ):
        page = principal_page
        page.goto(f"{live_server.url}/staff-affairs/assignments/")
        expect(page.locator("h1").first).to_contain_text("التكليفات")

        page.select_option("#f-assignee", value=str(e2e_deputy.pk))
        page.fill("input[name=reason]", "مهمّةٌ خارج المدرسة")
        page.click("button:has-text('تكليف')")

        page.wait_for_load_state("networkidle")
        expect(page.locator("main")).to_contain_text("نائب الاختبار")
        expect(page.locator("main")).to_contain_text("رفع التكليف")  # صفٌّ في «قائمةٌ اليوم»

    def test_a_teacher_cannot_open_the_assignments_screen(
        self, teacher_page, live_server, e2e_deputy
    ):
        response = teacher_page.goto(f"{live_server.url}/staff-affairs/assignments/")
        assert response is not None and response.status in (302, 403, 404)
        expect(teacher_page.locator("body")).not_to_contain_text("تكليفٌ جديد")


class TestAttendanceScreens:
    def test_the_secretary_opens_the_attendance_board(self, secretary_page, live_server):
        response = secretary_page.goto(f"{live_server.url}/staff-affairs/attendance/")
        assert response is not None and response.status == 200
        expect(secretary_page.locator("main")).to_be_visible()

    def test_the_principal_reaches_the_review_queue_and_the_report(
        self, principal_page, live_server
    ):
        for path in ("/staff-affairs/permits/review/", "/staff-affairs/attendance/report/"):
            response = principal_page.goto(f"{live_server.url}{path}")
            assert response is not None and response.status == 200, path
            expect(principal_page.locator("main")).to_be_visible()

    def test_every_employee_opens_his_own_permits_page(self, teacher_page, live_server):
        response = teacher_page.goto(f"{live_server.url}/staff-affairs/permits/mine/")
        assert response is not None and response.status == 200
        expect(teacher_page.locator("main")).to_contain_text("أذوناتي")
