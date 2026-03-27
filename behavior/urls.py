from django.urls import path

from . import views

app_name = "behavior"

urlpatterns = [
    path("dashboard/", views.behavior_dashboard, name="dashboard"),
    path("quick-log/", views.quick_log, name="quick_log"),
    path("report/", views.report_infraction, name="report_infraction"),
    path("student/<uuid:student_id>/", views.student_behavior_profile, name="student_profile"),
    path("recovery/<uuid:infraction_id>/", views.point_recovery_request, name="point_recovery"),
    # ✅ لجنة الضبط السلوكي
    path("committee/", views.committee_dashboard, name="committee"),
    path(
        "committee/<uuid:infraction_id>/decision/",
        views.committee_decision,
        name="committee_decision",
    ),
    # Phase 4 — تقارير سلوكية دورية
    path("report/student/<uuid:student_id>/", views.behavior_report, name="behavior_report"),
    path("statistics/", views.behavior_statistics, name="statistics"),
    # ✅ v5: PDF النماذج الثلاثة (Ct.zip × WeasyPrint)
    path(
        "infraction/<uuid:infraction_id>/pdf/warning/",
        views.infraction_warning_pdf,
        name="warning_pdf",
    ),
    path(
        "infraction/<uuid:infraction_id>/pdf/parent/",
        views.infraction_parent_pdf,
        name="parent_pdf",
    ),
    path(
        "infraction/<uuid:infraction_id>/pdf/student/",
        views.infraction_student_pdf,
        name="student_pdf",
    ),
    # ✅ v6: تصعيد + إحالة أمنية
    path(
        "infraction/<uuid:infraction_id>/escalate/",
        views.escalate_infraction,
        name="escalate_infraction",
    ),
    path(
        "infraction/<uuid:infraction_id>/security-referral/",
        views.security_referral,
        name="security_referral",
    ),
    # استدعاء ولي أمر
    path("summon/", views.summon_parent, name="summon_parent"),
    path("summon/<uuid:student_id>/", views.summon_parent, name="summon_parent_student"),
    # ✅ v7: تقرير سلوكي شامل للطالب — A4 للطباعة
    path(
        "student/<uuid:student_id>/pdf/",
        views.student_behavior_pdf,
        name="student_behavior_pdf",
    ),
    # ✅ v5: لائحة السلوك PDF — للموظفين + أولياء الأمور
    path("policy/pdf/", views.behavior_policy_pdf, name="policy_pdf"),
]
