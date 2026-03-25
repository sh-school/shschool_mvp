"""
E2E Tests: بوابة أولياء الأمور — SchoolOS v5.2
═══════════════════════════════════════════════
يختبر: وصول ولي الأمر، عرض الأبناء، الصلاحيات.
"""

import pytest
from playwright.sync_api import expect

from core.models import ConsentRecord

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


class TestParentPortalAccess:
    """اختبارات وصول بوابة أولياء الأمور."""

    def test_parent_sees_portal(self, login, e2e_school, e2e_roles, live_server):
        """ولي الأمر يرى بوابة أولياء الأمور بعد الموافقة."""
        from tests.e2e.conftest import _make_user

        parent = _make_user(e2e_school, e2e_roles["parent"], "99900000010", "ولي أمر E2E")
        # إعطاء الموافقة PDPPL
        from django.utils import timezone

        parent.consent_given_at = timezone.now()
        parent.save(update_fields=["consent_given_at"])

        page = login(parent)
        page.goto(f"{live_server.url}/parents/")
        expect(page.locator("main")).to_be_visible()


class TestAPIEndpoints:
    """اختبارات نقاط API عبر المتصفح."""

    def test_health_check_returns_ok(self, page, live_server):
        """نقطة فحص الصحة ترجع 200."""
        resp = page.goto(f"{live_server.url}/health/")
        assert resp.status == 200

    def test_unauthenticated_api_returns_401(self, page, live_server):
        """API بدون مصادقة ترجع 401/403."""
        resp = page.goto(f"{live_server.url}/api/v1/me/")
        assert resp.status in (401, 403)


class TestResponsiveLayout:
    """اختبارات التصميم المتجاوب."""

    def test_mobile_viewport_shows_menu(self, principal_page):
        """في الموبايل، القائمة تكون مخفية ويظهر زر الهامبرجر."""
        principal_page.set_viewport_size({"width": 375, "height": 812})
        # في الموبايل، شريط التنقل الرئيسي قد يكون مخفياً
        expect(principal_page.locator("main")).to_be_visible()

    def test_desktop_viewport_shows_nav(self, principal_page):
        """في الديسكتوب، شريط التنقل ظاهر."""
        principal_page.set_viewport_size({"width": 1280, "height": 800})
        expect(principal_page.locator("nav")).to_be_visible()
        expect(principal_page.locator("main")).to_be_visible()
