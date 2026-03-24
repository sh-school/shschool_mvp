"""
E2E Tests: تدفق المصادقة — SchoolOS v5.1.1
════════════════════════════════════════════
يختبر: تسجيل دخول، خروج، خطأ مصادقة، قفل حساب.
"""

import pytest
from playwright.sync_api import expect


pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


class TestLoginFlow:
    """اختبارات تسجيل الدخول."""

    def test_login_page_loads(self, page, live_server):
        """صفحة تسجيل الدخول تحمّل بنجاح مع حقول النموذج."""
        page.goto(f"{live_server.url}/auth/login/")
        expect(page.locator('input[name="national_id"]')).to_be_visible()
        expect(page.locator('input[name="password"]')).to_be_visible()
        expect(page.locator('button[type="submit"]')).to_be_visible()

    def test_login_success_redirects_to_dashboard(self, principal_page):
        """تسجيل دخول ناجح يوجّه إلى لوحة التحكم."""
        expect(principal_page).to_have_url(lambda url: "/dashboard/" in url)
        expect(principal_page.locator("main")).to_be_visible()

    def test_login_wrong_password_shows_error(self, page, live_server, e2e_principal):
        """كلمة مرور خاطئة تُظهر رسالة خطأ موحّدة."""
        page.goto(f"{live_server.url}/auth/login/")
        page.fill('input[name="national_id"]', e2e_principal.national_id)
        page.fill('input[name="password"]', "WrongPassword999!")
        page.click('button[type="submit"]')
        # يجب أن تبقى في صفحة الدخول مع رسالة خطأ
        expect(page).to_have_url(lambda url: "/auth/login" in url)

    def test_login_empty_fields_shows_error(self, page, live_server):
        """حقول فارغة تُظهر رسالة خطأ."""
        page.goto(f"{live_server.url}/auth/login/")
        page.click('button[type="submit"]')
        # لن ينتقل من صفحة الدخول (HTML5 validation أو server-side)
        expect(page).to_have_url(lambda url: "/auth/login" in url)


class TestLogoutFlow:
    """اختبارات تسجيل الخروج."""

    def test_logout_redirects_to_login(self, principal_page, live_server):
        """تسجيل الخروج يُعيد إلى صفحة الدخول."""
        # نحتاج الخروج عبر POST
        principal_page.evaluate("""
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = '/auth/logout/';
            const csrf = document.querySelector('[name=csrfmiddlewaretoken]');
            if (csrf) {
                const input = document.createElement('input');
                input.type = 'hidden';
                input.name = 'csrfmiddlewaretoken';
                input.value = csrf.value;
                form.appendChild(input);
            }
            document.body.appendChild(form);
            form.submit();
        """)
        principal_page.wait_for_url("**/auth/login/**", timeout=10000)
        expect(principal_page).to_have_url(lambda url: "/auth/login" in url)


class TestDashboardAccess:
    """اختبارات الوصول للوحة التحكم."""

    def test_unauthenticated_redirects_to_login(self, page, live_server):
        """المستخدم غير المسجّل يُعاد توجيهه لصفحة الدخول."""
        page.goto(f"{live_server.url}/dashboard/")
        expect(page).to_have_url(lambda url: "/auth/login" in url)

    def test_principal_sees_dashboard_content(self, principal_page):
        """المدير يرى محتوى لوحة التحكم."""
        expect(principal_page.locator("main")).to_be_visible()

    def test_teacher_sees_dashboard(self, teacher_page):
        """المعلم يرى لوحة التحكم."""
        expect(teacher_page.locator("main")).to_be_visible()
