from django.urls import path

from . import (
    views,
    views_daily,
    views_edit,
    views_escalation,
    views_exports,
    views_proposed_action,
)

app_name = "behavior"

urlpatterns = [
    path("dashboard/", views.behavior_dashboard, name="dashboard"),
    path("quick-log/", views.quick_log, name="quick_log"),
    path("escalation-preview/", views_escalation.escalation_preview, name="escalation_preview"),
    path("report/", views.report_infraction, name="report_infraction"),
    path("student/<uuid:student_id>/", views.student_behavior_profile, name="student_profile"),
    path(
        "student/<uuid:student_id>/xlsx/",
        views_exports.student_profile_xlsx,
        name="student_profile_xlsx",
    ),
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
    # تعديلُ مخالفةٍ مسجَّلة (بلاغ 5D5D)
    path(
        "infraction/<uuid:infraction_id>/edit/",
        views_edit.infraction_edit,
        name="infraction_edit",
    ),
    # اقتراحُ إجراء المخالفة واعتمادُه (W-20261112-003)
    path("actions/", views_proposed_action.proposed_actions, name="proposed_actions"),
    path(
        "actions/<uuid:infraction_id>/approve/",
        views_proposed_action.approve_action,
        name="approve_action",
    ),
    path(
        "actions/<uuid:infraction_id>/followup/",
        views_proposed_action.followup_action,
        name="followup_action",
    ),
    path(
        "actions/<uuid:infraction_id>/prepare/",
        views_proposed_action.prepare_action,
        name="prepare_action",
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
