from django.urls import path
from . import views

app_name = "behavior"

urlpatterns = [
    path("dashboard/",                               views.behavior_dashboard,       name="dashboard"),
    path("report/",                                  views.report_infraction,        name="report_infraction"),
    path("student/<uuid:student_id>/",               views.student_behavior_profile, name="student_profile"),
    path("recovery/<uuid:infraction_id>/",           views.point_recovery_request,   name="point_recovery"),
    # ✅ لجنة الضبط السلوكي
    path("committee/",                               views.committee_dashboard,      name="committee"),
    path("committee/<uuid:infraction_id>/decision/", views.committee_decision,       name="committee_decision"),

    # Phase 4 — تقارير سلوكية دورية
    path("report/student/<uuid:student_id>/",  views.behavior_report,     name="behavior_report"),
    path("statistics/",                        views.behavior_statistics,  name="statistics"),
]