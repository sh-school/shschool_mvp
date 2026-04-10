"""
academic_management/urls.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━
REQ-SH-002 — 10 routes for the restructured menu (stubs).
REQ-SH-003 — 5 routes for the academic reports landing + 4 report types.
"""

from django.urls import path

from . import views

app_name = "academic_management"

urlpatterns = [
    # ── REQ-SH-002 — submenu stubs ────────────────────────────────
    path("evaluations/", views.evaluations, name="evaluations"),
    path("departments/", views.departments, name="departments"),
    path("test-analytics/", views.test_analytics, name="test_analytics"),
    path("workload/", views.workload, name="workload"),
    path("assignments/", views.assignments, name="assignments"),
    path("department-reports/", views.department_reports, name="department_reports"),
    path("classroom-visits/", views.classroom_visits, name="classroom_visits"),
    path("e-learning/", views.elearning, name="elearning"),
    path("class-performance/", views.class_performance, name="class_performance"),
    path("underperformance/", views.underperformance, name="underperformance"),
    # ── REQ-SH-003 — Academic Reports (4 report types) ───────────
    path("reports/", views.reports_landing, name="reports_landing"),
    path("reports/quiz/", views.quiz_reports, name="quiz_reports"),
    path(
        "reports/exam-results/",
        views.exam_results_reports,
        name="exam_results_reports",
    ),
    path(
        "reports/progress/",
        views.academic_progress_reports,
        name="academic_progress_reports",
    ),
    path(
        "reports/monthly-behavior-academic/",
        views.monthly_ba_report,
        name="monthly_ba_report",
    ),
]
