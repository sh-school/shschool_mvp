"""
tests/test_academic_management.py — REQ-SH-002
Smoke tests for the 10 stub pages under إدارة الشؤون الأكاديمية.
Client #001 (Shahaniya School) menu restructure.
"""

import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestAcademicManagementStubs:
    """Verify all 10 stub pages render correctly for authenticated users."""

    STUB_URLS = [
        ("academic_management:evaluations", "التقييمات والدرجات"),
        ("academic_management:departments", "إدارة الأقسام التعليمية"),
        ("academic_management:test_analytics", "تحليلات الاختبارات"),
        ("academic_management:workload", "إسناد الأنصبة"),
        ("academic_management:assignments", "التكاليف"),
        ("academic_management:department_reports", "التقارير الخاصة بالقسم"),
        ("academic_management:classroom_visits", "الزيارات الصفية"),
        ("academic_management:elearning", "التعليم الإلكتروني"),
        ("academic_management:class_performance", "تقارير الأداء الصفي"),
        ("academic_management:underperformance", "إدارة الأداء دون المستوى"),
    ]

    def test_all_stub_pages_render_for_principal(self, client_as, principal_user):
        """All 10 stub pages return HTTP 200 with correct Arabic label + 'قيد التطوير'."""
        c = client_as(principal_user)

        for url_name, expected_label in self.STUB_URLS:
            url = reverse(url_name)
            response = c.get(url)

            assert response.status_code == 200, (
                f"{url_name} returned {response.status_code} (expected 200)"
            )

            content = response.content.decode("utf-8")
            assert expected_label in content, (
                f"{url_name} missing expected label '{expected_label}'"
            )
            assert "قيد التطوير" in content, f"{url_name} missing 'under construction' notice"
            assert "إدارة الشؤون الأكاديمية" in content, f"{url_name} missing module name"

    def test_stub_pages_require_login(self, client):
        """Unauthenticated users should be redirected (login_required)."""
        url = reverse("academic_management:evaluations")
        response = client.get(url)
        # login_required redirects to LOGIN_URL
        assert response.status_code in (302, 301), (
            f"Unauthenticated request should redirect, got {response.status_code}"
        )

    def test_menu_label_updated_in_base_template(self, client_as, principal_user):
        """Verify the renamed header label 'إدارة الشؤون الأكاديمية' appears in nav."""
        c = client_as(principal_user)
        response = c.get(reverse("academic_management:evaluations"))
        content = response.content.decode("utf-8")
        # New label must be present (via base.html nav)
        assert "إدارة الشؤون الأكاديمية" in content

    def test_all_ten_routes_exist(self):
        """Ensure exactly 10 URL patterns are registered."""
        assert len(self.STUB_URLS) == 10, "REQ-SH-002 requires exactly 10 submenu items"
        # Verify all reverse
        for url_name, _ in self.STUB_URLS:
            url = reverse(url_name)
            assert url.startswith("/academic/"), f"{url_name} should be under /academic/, got {url}"
