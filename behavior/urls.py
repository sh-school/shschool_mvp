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

    # ✅ v5: PDF النماذج الثلاثة (Ct.zip × WeasyPrint)
    path("infraction/<uuid:infraction_id>/pdf/warning/",  views.infraction_warning_pdf, name="warning_pdf"),
    path("infraction/<uuid:infraction_id>/pdf/parent/",   views.infraction_parent_pdf,  name="parent_pdf"),
    path("infraction/<uuid:infraction_id>/pdf/student/",  views.infraction_student_pdf, name="student_pdf"),
    # ✅ v5: لائحة السلوك PDF — للموظفين + أولياء الأمور
    path("policy/pdf/", views.behavior_policy_pdf, name="policy_pdf"),

    # ✅ v5+: Word (.docx) النماذج الثلاثة + اللائحة
    path("infraction/<uuid:infraction_id>/word/warning/",  views.infraction_warning_word, name="warning_word"),
    path("infraction/<uuid:infraction_id>/word/parent/",   views.infraction_parent_word,  name="parent_word"),
    path("infraction/<uuid:infraction_id>/word/student/",  views.infraction_student_word, name="student_word"),
    path("policy/word/", views.behavior_policy_word, name="policy_word"),
]