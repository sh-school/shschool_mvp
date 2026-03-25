"""
E2E Tests: تدفق الدرجات والتقييمات — SchoolOS v5.2
════════════════════════════════════════════════════
يختبر: عرض الدرجات، التنقل بين صفحات التقييم، التحقق من الوصول.
"""

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


class TestAssessmentsAccess:
    """اختبارات وصول صفحة التقييمات."""

    def test_principal_can_access_assessments(self, principal_page, live_server):
        """المدير يستطيع الوصول لصفحة التقييمات."""
        principal_page.goto(f"{live_server.url}/assessments/")
        expect(principal_page.locator("main")).to_be_visible()
        expect(principal_page).to_have_url(lambda url: "/assessments/" in url)

    def test_teacher_can_access_assessments(self, teacher_page, live_server):
        """المعلم يستطيع الوصول لصفحة التقييمات."""
        teacher_page.goto(f"{live_server.url}/assessments/")
        expect(teacher_page.locator("main")).to_be_visible()

    def test_student_cannot_access_assessments(self, login, e2e_student, live_server):
        """الطالب لا يستطيع الوصول لصفحة التقييمات (403)."""
        page = login(e2e_student)
        resp = page.goto(f"{live_server.url}/assessments/")
        # يجب أن يُعاد توجيهه أو يحصل على 403
        url = page.url
        assert "/assessments/" not in url or resp.status == 403


class TestReportsAccess:
    """اختبارات وصول صفحة التقارير."""

    def test_principal_can_access_reports(self, principal_page, live_server):
        """المدير يستطيع الوصول لصفحة التقارير."""
        principal_page.goto(f"{live_server.url}/reports/")
        expect(principal_page.locator("main")).to_be_visible()

    def test_reports_page_has_content(self, principal_page, live_server):
        """صفحة التقارير تحتوي محتوى."""
        principal_page.goto(f"{live_server.url}/reports/")
        main = principal_page.locator("main")
        expect(main).to_be_visible()
