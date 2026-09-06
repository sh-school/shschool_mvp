"""
academic_management/urls.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━
REQ-SH-002 — 9 routes for the restructured menu (stubs).
REQ-SH-003 — 5 routes for the academic reports landing + 4 report types.
"""

from django.urls import path

from . import assignment_views, views

app_name = "academic_management"

urlpatterns = [
    # ── REQ-SH-002 — submenu stubs ────────────────────────────────
    path("evaluations/", views.evaluations, name="evaluations"),
    path("departments/", views.departments, name="departments"),
    path("test-analytics/", views.test_analytics, name="test_analytics"),
    path("assignments/", assignment_views.assignments, name="assignments"),
    path(
        "assignments/subjects/", assignment_views.subject_options, name="assignment_subject_options"
    ),
    path("assignments/<uuid:teacher_id>/add/", assignment_views.add_row, name="assignment_add_row"),
    path(
        "assignments/<uuid:teacher_id>/load/", assignment_views.set_load, name="assignment_set_load"
    ),
    path(
        "assignments/<uuid:teacher_id>/cancel-transfer/",
        assignment_views.cancel_transfer,
        name="assignment_cancel_transfer",
    ),
    path(
        "assignments/<uuid:teacher_id>/department/",
        assignment_views.set_department,
        name="assignment_set_department",
    ),
    path(
        "assignments/<uuid:teacher_id>/preparation/",
        assignment_views.toggle_preparation,
        name="assignment_toggle_preparation",
    ),
    path(
        "assignments/row/<uuid:assignment_id>/periods/",
        assignment_views.update_periods,
        name="assignment_update_periods",
    ),
    path(
        "assignments/row/<uuid:assignment_id>/remove/",
        assignment_views.remove_row,
        name="assignment_remove_row",
    ),
    path(
        "assignments/<uuid:teacher_id>/<slug:action>/",
        assignment_views.move,
        name="assignment_move",
    ),
    path("department-reports/", views.department_reports, name="department_reports"),
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
