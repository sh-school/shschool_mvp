"""
tests/test_analytics_reports.py
اختبارات التحليلات والتقارير

يغطي:
  - Analytics: APIs ترجع JSON صحيح
  - Reports: PDF/Excel generation لا يرمي أخطاء
  - التحقق من الصلاحيات — فقط الإدارة
"""

import json

import pytest

from assessments.models import SubjectClassSetup
from operations.models import Subject


@pytest.fixture
def subject(db, school):
    return Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")


@pytest.fixture
def setup_with_data(db, school, subject, class_group, teacher_user):
    return SubjectClassSetup.objects.create(
        school=school,
        subject=subject,
        class_group=class_group,
        teacher=teacher_user,
        academic_year="2025-2026",
    )


# ══════════════════════════════════════════════════
#  Analytics Views
# ══════════════════════════════════════════════════


class TestAnalyticsViews:
    def test_dashboard_as_principal(self, client_as, principal_user):
        c = client_as(principal_user)
        resp = c.get("/analytics/")
        assert resp.status_code == 200

    def test_dashboard_forbidden_for_teacher(self, client_as, teacher_user):
        c = client_as(teacher_user)
        resp = c.get("/analytics/")
        assert resp.status_code == 403

    def test_api_attendance_trend(self, client_as, principal_user):
        c = client_as(principal_user)
        resp = c.get("/analytics/api/attendance-trend/")
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert isinstance(data, (dict, list))

    def test_api_grades_distribution(self, client_as, principal_user):
        c = client_as(principal_user)
        resp = c.get("/analytics/api/grades-distribution/")
        assert resp.status_code == 200

    def test_api_class_comparison(self, client_as, principal_user):
        c = client_as(principal_user)
        resp = c.get("/analytics/api/class-comparison/")
        assert resp.status_code == 200

    def test_api_subject_comparison(self, client_as, principal_user):
        c = client_as(principal_user)
        resp = c.get("/analytics/api/subject-comparison/")
        assert resp.status_code == 200

    def test_api_plan_progress(self, client_as, principal_user):
        c = client_as(principal_user)
        resp = c.get("/analytics/api/plan-progress/")
        assert resp.status_code == 200

    def test_api_failing_by_class(self, client_as, principal_user):
        c = client_as(principal_user)
        resp = c.get("/analytics/api/failing-by-class/")
        assert resp.status_code == 200

    def test_api_behavior_trend(self, client_as, principal_user):
        c = client_as(principal_user)
        resp = c.get("/analytics/api/behavior-trend/")
        assert resp.status_code == 200

    def test_api_clinic_stats(self, client_as, principal_user):
        c = client_as(principal_user)
        resp = c.get("/analytics/api/clinic-stats/")
        assert resp.status_code == 200

    def test_all_apis_return_json(self, client_as, principal_user):
        """كل APIs التحليلات ترجع JSON صالح"""
        c = client_as(principal_user)
        endpoints = [
            "/analytics/api/attendance-trend/",
            "/analytics/api/grades-distribution/",
            "/analytics/api/class-comparison/",
            "/analytics/api/subject-comparison/",
            "/analytics/api/plan-progress/",
            "/analytics/api/failing-by-class/",
            "/analytics/api/behavior-trend/",
            "/analytics/api/clinic-stats/",
        ]
        for url in endpoints:
            resp = c.get(url)
            assert resp.status_code == 200, f"Failed: {url}"
            assert resp["Content-Type"] == "application/json", f"Not JSON: {url}"


# ══════════════════════════════════════════════════
#  Reports Views
# ══════════════════════════════════════════════════


class TestReportsViews:
    def test_reports_index(self, client_as, principal_user):
        c = client_as(principal_user)
        resp = c.get("/reports/")
        assert resp.status_code == 200

    def test_reports_forbidden_for_student(self, client_as, student_user):
        c = client_as(student_user)
        resp = c.get("/reports/")
        assert resp.status_code == 403

    def test_class_results_pdf(self, client_as, principal_user, class_group):
        c = client_as(principal_user)
        resp = c.get(f"/reports/class/{class_group.id}/results/")
        # 200 = HTML fallback عند عدم وجود طلاب، أو PDF عند وجود بيانات
        assert resp.status_code == 200

    def test_attendance_report(self, client_as, principal_user, class_group):
        c = client_as(principal_user)
        resp = c.get(f"/reports/class/{class_group.id}/attendance/")
        assert resp.status_code == 200

    def test_student_result_pdf(self, client_as, teacher_user, student_user):
        c = client_as(teacher_user)
        resp = c.get(f"/reports/student/{student_user.id}/result/")
        assert resp.status_code == 200

    def test_class_results_excel(self, client_as, principal_user, class_group):
        c = client_as(principal_user)
        resp = c.get(f"/reports/class/{class_group.id}/results/excel/")
        assert resp.status_code == 200
        assert "spreadsheet" in resp["Content-Type"] or "excel" in resp["Content-Type"].lower()

    def test_attendance_excel(self, client_as, principal_user, class_group):
        c = client_as(principal_user)
        resp = c.get(f"/reports/class/{class_group.id}/attendance/excel/")
        assert resp.status_code == 200

    def test_behavior_excel(self, client_as, principal_user):
        c = client_as(principal_user)
        resp = c.get("/reports/behavior/excel/")
        assert resp.status_code == 200
