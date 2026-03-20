from django.urls import path
from . import views

urlpatterns = [
    path("",                         views.analytics_dashboard,      name="analytics_dashboard"),
    path("api/attendance-trend/",    views.api_attendance_trend,     name="api_att_trend"),
    path("api/grades-distribution/", views.api_grades_distribution,  name="api_grades_dist"),
    path("api/class-comparison/",    views.api_class_comparison,     name="api_class_cmp"),
    path("api/subject-comparison/",  views.api_subject_comparison,   name="api_subj_cmp"),
    # path("api/teacher-performance/", views.api_teacher_performance,  name="api_teacher_perf"),  # تم التعليق بسبب عدم وجود الدالة
    path("api/plan-progress/",       views.api_plan_progress,        name="api_plan_prog"),
    path("api/failing-by-class/",    views.api_failing_by_class,     name="api_fail_cls"),
    # ✅ جديد
    path("api/behavior-trend/",      views.api_behavior_trend,       name="api_behavior_trend"),
    path("api/clinic-stats/",        views.api_clinic_stats,         name="api_clinic_stats"),
    # ✅ v5: لوحة KPIs العشرة (Ct.zip)
    path("kpis/",                    views.kpi_dashboard,            name="kpi_dashboard"),
    path("api/kpis/",                views.api_kpis_all,             name="api_kpis_all"),
]
