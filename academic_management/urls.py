"""
academic_management/urls.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━
REQ-SH-002 — 9 routes for the restructured menu (stubs).
REQ-SH-003 — 5 routes for the academic reports landing + 4 report types.
"""

from django.urls import path

from . import views, workload_views

app_name = "academic_management"

urlpatterns = [
    # ── REQ-SH-002 — submenu stubs ────────────────────────────────
    path("evaluations/", views.evaluations, name="evaluations"),
    path("departments/", views.departments, name="departments"),
    path("test-analytics/", views.test_analytics, name="test_analytics"),
    path("workload/", views.workload, name="workload"),
    # ── خطّةُ النصاب: قراءةٌ في مسار، وأوامرُ في مسارات ─────────────
    # الفصلُ مقصود: `/workload/` مرصدٌ لا يكتب، والكتابةُ لمعلّمٍ واحدٍ وخطّةٍ
    # واحدةٍ في كلّ مرّة. وشبكةٌ جماعيّةٌ قابلةٌ للكتابة تُغري بالحشو السريع
    # وتُخفي أنّ كلَّ سطرٍ فيها قرارٌ إداريٌّ له مصدر.
    path(
        "workload/teacher/<uuid:teacher_id>/",
        workload_views.teacher_workload,
        name="teacher_workload",
    ),
    path(
        "workload/teacher/<uuid:teacher_id>/draft/",
        workload_views.open_draft,
        name="open_draft",
    ),
    path("workload/plan/<uuid:plan_id>/edit/", workload_views.plan_editor, name="plan_editor"),
    path("workload/plan/<uuid:plan_id>/head/", workload_views.edit_head, name="edit_head"),
    path(
        "workload/plan/<uuid:plan_id>/reduction/",
        workload_views.edit_reduction,
        name="edit_reduction",
    ),
    path(
        "workload/plan/<uuid:plan_id>/allocation/",
        workload_views.add_allocation,
        name="add_allocation",
    ),
    path(
        "workload/plan/<uuid:plan_id>/allocation/<int:allocation_id>/delete/",
        workload_views.delete_allocation,
        name="delete_allocation",
    ),
    path(
        "workload/plan/<uuid:plan_id>/validate/", workload_views.validate_plan, name="validate_plan"
    ),
    path("workload/plan/<uuid:plan_id>/submit/", workload_views.submit_plan, name="submit_plan"),
    path("workload/plan/<uuid:plan_id>/review/", workload_views.plan_review, name="plan_review"),
    path(
        "workload/plan/<uuid:plan_id>/review/record/",
        workload_views.review_plan,
        name="review_plan",
    ),
    path("workload/plan/<uuid:plan_id>/return/", workload_views.return_plan, name="return_plan"),
    path("workload/plan/<uuid:plan_id>/approve/", workload_views.approve_plan, name="approve_plan"),
    path("workload/plan/<uuid:plan_id>/lock/", workload_views.lock_plan, name="lock_plan"),
    path("workload/plan/<uuid:plan_id>/revise/", workload_views.revise_plan, name="revise_plan"),
    path("assignments/", views.assignments, name="assignments"),
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
