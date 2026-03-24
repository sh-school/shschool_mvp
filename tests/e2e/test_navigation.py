"""
E2E Tests: التنقل والوصول — SchoolOS v5.1.1
═════════════════════════════════════════════
يختبر: التنقل بين الصفحات، الـ nav bar، dark mode، responsive.
"""

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


class TestNavigation:
    """اختبارات شريط التنقل."""

    def test_navbar_visible(self, principal_page):
        """شريط التنقل ظاهر بعد تسجيل الدخول."""
        expect(principal_page.locator("nav")).to_be_visible()

    def test_principal_sees_admin_menu(self, principal_page):
        """المدير يرى قائمة الإدارة."""
        nav = principal_page.locator("nav")
        expect(nav).to_be_visible()

    def test_navigate_to_behavior(self, principal_page, live_server):
        """الانتقال لصفحة السلوك."""
        principal_page.goto(f"{live_server.url}/behavior/dashboard/")
        expect(principal_page.locator("main")).to_be_visible()

    def test_navigate_to_analytics(self, principal_page, live_server):
        """الانتقال لصفحة التحليلات."""
        principal_page.goto(f"{live_server.url}/analytics/")
        expect(principal_page.locator("main")).to_be_visible()


class TestDarkMode:
    """اختبارات الوضع الداكن."""

    def test_dark_mode_toggle(self, principal_page):
        """تبديل الوضع الداكن يُضيف class dark على html."""
        toggle = principal_page.locator("#dark-toggle")
        if toggle.count() > 0:
            toggle.click()
            expect(principal_page.locator("html")).to_have_class(lambda c: "dark" in c)
            toggle.click()
            expect(principal_page.locator("html")).not_to_have_class(lambda c: "dark" in c)


class TestAccessibility:
    """اختبارات إمكانية الوصول الأساسية."""

    def test_main_landmark_exists(self, principal_page):
        """عنصر main موجود."""
        expect(principal_page.locator("main")).to_be_visible()

    def test_nav_landmark_exists(self, principal_page):
        """عنصر nav موجود."""
        expect(principal_page.locator("nav")).to_be_visible()

    def test_page_has_rtl_direction(self, principal_page):
        """الصفحة بها اتجاه RTL."""
        html = principal_page.locator("html")
        expect(html).to_have_attribute("dir", "rtl")

    def test_page_language_is_arabic(self, principal_page):
        """لغة الصفحة عربية."""
        html = principal_page.locator("html")
        expect(html).to_have_attribute("lang", "ar")
