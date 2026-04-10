"""
academic_management/urls.py — REQ-SH-002
10 routes for the restructured "إدارة الشؤون الأكاديمية" menu.
Stub phase: each route renders a placeholder "قيد التطوير" page.
"""

from django.urls import path

from . import views

app_name = "academic_management"

urlpatterns = [
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
]
