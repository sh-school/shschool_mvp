from django.urls import path

from . import views, views_actions, views_daily, views_escalation

app_name = "behavior"

urlpatterns = [
    path("dashboard/", views.behavior_dashboard, name="dashboard"),
    path("quick-log/", views.quick_log, name="quick_log"),
    path("escalation-preview/", views_escalation.escalation_preview, name="escalation_preview"),
    path("report/", views.report_infraction, name="report_infraction"),
    # إجراء المخالفة: تجهيزُ المشرف، ومتابعةُ المنسّق واعتمادُه، وقائمةُ الاختصاصيَّين (W-20261108-005)
    path("actions/", views_actions.approvals, name="actions"),
    path("actions/prepare/", views_actions.prepare_list, name="actions_prepare"),
    path("actions/specialists/", views_actions.specialist_list, name="actions_specialists"),
    path("actions/<uuid:infraction_id>/prepare/", views_actions.prepare, name="action_prepare"),
    path("actions/<uuid:infraction_id>/followup/", views_actions.followup, name="action_followup"),
    path("actions/<uuid:infraction_id>/approve/", views_actions.approve, name="action_approve"),
    path("student/<uuid:student_id>/", views.student_behavior_profile, name="student_profile"),
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
    # التقرير السلوكيّ اليوميّ بتاريخ يوم، وتصديرُه PDF وExcel عبر مركز التصدير
    path("daily/", views_daily.daily_report_page, name="daily_report"),
    path("daily/pdf/", views_daily.daily_report_pdf, name="daily_report_pdf"),
    path("daily/xlsx/", views_daily.daily_report_xlsx, name="daily_report_xlsx"),
    # لائحةُ السلوك — وثيقةُ مدرسةٍ لا مخالفة (للموظفين وأولياء الأمور). كان المسارُ
    # مكرَّراً في آخر القائمة بالاسم نفسِه — والأوّلُ وحدَه يُحلّ، فحُذف الثاني.
    path("policy/pdf/", views.behavior_policy_pdf, name="policy_pdf"),
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
]
