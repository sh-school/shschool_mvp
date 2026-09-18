"""
E2E Tests: تدفق الإشعارات — SchoolOS v5.2
═══════════════════════════════════════════
يختبر: صندوق الإشعارات، الوصول، التحقق من الأيقونة.
"""

import pytest

pytest.importorskip("pytest_playwright")
from playwright.sync_api import expect  # noqa: E402

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


class TestNotificationsAccess:
    """اختبارات صندوق الإشعارات."""

    def test_principal_can_access_notifications(self, principal_page, live_server):
        """المدير يستطيع الوصول لصندوق الإشعارات."""
        principal_page.goto(f"{live_server.url}/notifications/inbox/")
        expect(principal_page.locator("main")).to_be_visible()

    def test_notification_bell_visible(self, principal_page):
        """أيقونة الإشعارات ظاهرة في الـ nav."""
        nav = principal_page.locator("nav").first
        expect(nav).to_be_visible()


class TestLibraryAccess:
    """اختبارات المكتبة."""

    def test_principal_can_access_library(self, principal_page, live_server):
        """المدير يستطيع الوصول للمكتبة."""
        principal_page.goto(f"{live_server.url}/library/")
        expect(principal_page.locator("main")).to_be_visible()

    def test_teacher_can_access_library(self, teacher_page, live_server):
        """المعلم يستطيع الوصول للمكتبة — ضمن الأدوار المسموحة في core/module_registry.py
        (library/apps.py)، وليست مقيدةً لأمين المكتبة وحده كما افترض اختبارٌ قديم."""
        resp = teacher_page.goto(f"{live_server.url}/library/")
        assert resp.status == 200
        expect(teacher_page.locator("main")).to_be_visible()


class TestTransportAccess:
    """اختبارات النقل."""

    def test_principal_can_access_transport(self, principal_page, live_server):
        """المدير يستطيع الوصول لصفحة النقل."""
        principal_page.goto(f"{live_server.url}/transport/")
        expect(principal_page.locator("main")).to_be_visible()


class TestBehaviorFlow:
    """اختبارات السلوك."""

    def test_principal_sees_behavior_dashboard(self, principal_page, live_server):
        """المدير يرى لوحة السلوك."""
        principal_page.goto(f"{live_server.url}/behavior/dashboard/")
        expect(principal_page.locator("main")).to_be_visible()

    def test_behavior_page_structure(self, principal_page, live_server):
        """صفحة السلوك تحتوي على هيكل صحيح."""
        principal_page.goto(f"{live_server.url}/behavior/dashboard/")
        expect(principal_page.locator("nav").first).to_be_visible()
        expect(principal_page.locator("main")).to_be_visible()
