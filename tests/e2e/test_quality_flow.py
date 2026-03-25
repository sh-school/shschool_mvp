"""
E2E Tests: تدفق إدارة الجودة — SchoolOS v5.2
═══════════════════════════════════════════════
يختبر: لوحة الجودة، الخطط التشغيلية، التنقل.
"""

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


class TestQualityDashboard:
    """اختبارات لوحة الجودة."""

    def test_principal_can_access_quality(self, principal_page, live_server):
        """المدير يستطيع الوصول للوحة الجودة."""
        principal_page.goto(f"{live_server.url}/quality/")
        expect(principal_page.locator("main")).to_be_visible()
        expect(principal_page).to_have_url(lambda url: "/quality/" in url)

    def test_quality_page_loads_structure(self, principal_page, live_server):
        """صفحة الجودة تحمّل بالهيكل الصحيح."""
        principal_page.goto(f"{live_server.url}/quality/")
        expect(principal_page.locator("main")).to_be_visible()
        expect(principal_page.locator("nav")).to_be_visible()


class TestClinicAccess:
    """اختبارات وصول العيادة."""

    def test_principal_can_access_clinic(self, principal_page, live_server):
        """المدير يستطيع الوصول للعيادة."""
        principal_page.goto(f"{live_server.url}/clinic/")
        expect(principal_page.locator("main")).to_be_visible()

    def test_teacher_cannot_access_clinic(self, teacher_page, live_server):
        """المعلم لا يستطيع الوصول للعيادة."""
        resp = teacher_page.goto(f"{live_server.url}/clinic/")
        url = teacher_page.url
        # يحصل على 403 أو يُعاد توجيهه
        assert "/clinic/" not in url or resp.status == 403


class TestExamControlAccess:
    """اختبارات وصول كنترول الامتحانات."""

    def test_principal_can_access_exam_control(self, principal_page, live_server):
        """المدير يستطيع الوصول لكنترول الامتحانات."""
        principal_page.goto(f"{live_server.url}/exam-control/")
        expect(principal_page.locator("main")).to_be_visible()
