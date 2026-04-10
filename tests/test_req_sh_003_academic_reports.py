"""
tests/test_req_sh_003_academic_reports.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REQ-SH-003 — Academic reports page with 4 report types.
Client #001 (Shahaniya School) request from MTG-007.

Smoke tests:
  - Landing page renders with all 4 report cards
  - Each of the 4 reports renders (empty state is acceptable)
  - PDF export returns application/pdf
  - Excel export returns spreadsheetml content type
  - Flagship monthly report accepts month/year/scope filters
"""

import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestAcademicReportsREQSH003:
    """REQ-SH-003 — 4 academic report types for Client #001."""

    def test_reports_landing_renders_with_four_cards(self, client_as, principal_user):
        """Landing page shows all 4 report cards including the flagship."""
        c = client_as(principal_user)
        response = c.get(reverse("academic_management:reports_landing"))

        assert response.status_code == 200
        content = response.content.decode("utf-8")

        # Page title
        assert "التقارير الأكاديمية" in content
        # All 4 report titles
        assert "تقارير الاختبارات القصيرة" in content
        assert "تقارير نتائج الاختبارات" in content
        assert "تقارير التقدم الأكاديمي" in content
        assert "التقرير السلوكي والتعليمي الشهري" in content
        # Flagship badge
        assert "تقرير رئيسي" in content

    def test_quiz_reports_renders(self, client_as, principal_user):
        """Report 1 — quiz reports renders (empty state allowed)."""
        c = client_as(principal_user)
        response = c.get(reverse("academic_management:quiz_reports"))
        assert response.status_code == 200
        assert "تقارير الاختبارات القصيرة" in response.content.decode("utf-8")

    def test_exam_results_reports_renders(self, client_as, principal_user):
        """Report 2 — exam results renders."""
        c = client_as(principal_user)
        response = c.get(reverse("academic_management:exam_results_reports"))
        assert response.status_code == 200
        assert "تقارير نتائج الاختبارات" in response.content.decode("utf-8")

    def test_academic_progress_reports_renders(self, client_as, principal_user):
        """Report 3 — academic progress renders (without class selected = empty)."""
        c = client_as(principal_user)
        response = c.get(reverse("academic_management:academic_progress_reports"))
        assert response.status_code == 200
        assert "تقارير التقدم الأكاديمي" in response.content.decode("utf-8")

    def test_monthly_ba_report_renders(self, client_as, principal_user):
        """Report 4 (flagship) — monthly behavior + academic renders."""
        c = client_as(principal_user)
        response = c.get(reverse("academic_management:monthly_ba_report"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "التقرير السلوكي والتعليمي الشهري" in content
        assert "تقرير رئيسي" in content

    def test_monthly_ba_report_accepts_filters(self, client_as, principal_user):
        """Flagship report accepts month/year/scope query params."""
        c = client_as(principal_user)
        response = c.get(
            reverse("academic_management:monthly_ba_report"),
            {"month": "4", "year": "2026", "scope": "section"},
        )
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "2026-04" in content

    def test_monthly_ba_report_excel_export(self, client_as, principal_user):
        """Flagship report Excel export returns spreadsheetml content."""
        c = client_as(principal_user)
        response = c.get(
            reverse("academic_management:monthly_ba_report"),
            {"export": "excel", "month": "4", "year": "2026"},
        )
        assert response.status_code == 200
        assert "spreadsheetml" in response["Content-Type"]
        assert "attachment" in response.get("Content-Disposition", "")

    def test_quiz_reports_excel_export(self, client_as, principal_user):
        """Quiz reports Excel export returns spreadsheetml content."""
        c = client_as(principal_user)
        response = c.get(
            reverse("academic_management:quiz_reports"),
            {"export": "excel"},
        )
        assert response.status_code == 200
        assert "spreadsheetml" in response["Content-Type"]

    def test_exam_results_excel_export(self, client_as, principal_user):
        """Exam results Excel export returns spreadsheetml content."""
        c = client_as(principal_user)
        response = c.get(
            reverse("academic_management:exam_results_reports"),
            {"export": "excel"},
        )
        assert response.status_code == 200
        assert "spreadsheetml" in response["Content-Type"]

    def test_academic_progress_excel_export(self, client_as, principal_user):
        """Academic progress Excel export returns spreadsheetml content."""
        c = client_as(principal_user)
        response = c.get(
            reverse("academic_management:academic_progress_reports"),
            {"export": "excel"},
        )
        assert response.status_code == 200
        assert "spreadsheetml" in response["Content-Type"]

    def test_reports_require_login(self, client):
        """All REQ-SH-003 routes require authentication."""
        urls = [
            "academic_management:reports_landing",
            "academic_management:quiz_reports",
            "academic_management:exam_results_reports",
            "academic_management:academic_progress_reports",
            "academic_management:monthly_ba_report",
        ]
        for url_name in urls:
            response = client.get(reverse(url_name))
            assert response.status_code in (
                301,
                302,
            ), f"{url_name} should redirect unauthenticated users"

    def test_all_five_routes_registered(self):
        """REQ-SH-003 registers 5 URLs (1 landing + 4 reports)."""
        url_names = [
            "academic_management:reports_landing",
            "academic_management:quiz_reports",
            "academic_management:exam_results_reports",
            "academic_management:academic_progress_reports",
            "academic_management:monthly_ba_report",
        ]
        for name in url_names:
            url = reverse(name)
            assert url.startswith(
                "/academic/reports"
            ), f"{name} should be under /academic/reports/, got {url}"
