from django.urls import path

from . import views
from .views_attendance_entries import (
    approval_decide,
    approvals,
    approve_session,
    approve_session_defaults,
    correct_page,
    correct_submit,
    entry_submit,
    period_entries,
    unapproved,
)
from .views_class_grid import (
    class_grid,
    class_grid_exit,
    class_grid_history,
    class_grid_late,
    class_grid_save,
)
from .views_director_live import director_live
from .views_provisional import provisional_class, provisional_classes, provisional_create
from .views_schedule_drafts import discard_schedule, stop_schedule_generation

urlpatterns = [
    path("schedule/", views.schedule, name="teacher_schedule"),
    # الاستطلاعُ الحيّ للوحة المدير (W-20261008-004، D-249م القسم 9): JSON بلا أسماء، للمدير ونائبيه.
    path("director-live/", director_live, name="director_live"),
    # -- رصدٌ بحصّةٍ مؤقّتة للمعلّم قبل اعتماد الجدول (W-20261005-006؛ مطفأٌ بمفتاح PROVISIONAL_SESSIONS_ENABLED) --
    path("classes/", provisional_classes, name="provisional_classes"),
    path("classes/<uuid:class_id>/", provisional_class, name="provisional_class"),
    path("classes/<uuid:class_id>/period/", provisional_create, name="provisional_create"),
    # -- جدولُ الشعبة العموديّ لرصد الغياب (W-20261006-005؛ مطفأٌ بمفتاح PROVISIONAL_GRID_ENABLED ← 404) --
    path("classes/<uuid:class_id>/grid/", class_grid, name="class_grid"),
    path("classes/<uuid:class_id>/grid/save/", class_grid_save, name="class_grid_save"),
    path("classes/<uuid:class_id>/grid/late/", class_grid_late, name="class_grid_late"),
    path("classes/<uuid:class_id>/grid/exit/", class_grid_exit, name="class_grid_exit"),
    path(
        "classes/<uuid:class_id>/grid/history/<uuid:student_id>/<int:number>/",
        class_grid_history,
        name="class_grid_history",
    ),
    # -- رصدُ المعلّم المبدئيّ واعتمادُه (W-020) --
    path("attendance/approvals/", approvals, name="attendance_approvals"),
    path(
        "attendance/approvals/session/<uuid:session_id>/approve/",
        approve_session,
        name="attendance_approve_session",
    ),
    path(
        "attendance/approvals/session/<uuid:session_id>/approve-defaults/",
        approve_session_defaults,
        name="attendance_approve_defaults",
    ),
    path("attendance/approvals/<uuid:entry_id>/decide/", approval_decide, name="attendance_decide"),
    path("attendance/unapproved/", unapproved, name="attendance_unapproved"),
    path("attendance/<uuid:session_id>/entry/", entry_submit, name="attendance_entry"),
    path("attendance/<uuid:session_id>/entries/", period_entries, name="attendance_period_entries"),
    path("attendance/<uuid:session_id>/correct/", correct_page, name="attendance_correct"),
    path(
        "attendance/<uuid:session_id>/correct/submit/",
        correct_submit,
        name="attendance_correct_submit",
    ),
    path("attendance/<uuid:session_id>/", views.attendance_view, name="attendance"),
    path("attendance/<uuid:session_id>/mark-single/", views.mark_single, name="mark_single"),
    path("attendance/<uuid:session_id>/mark-all/", views.mark_all_present, name="mark_all_present"),
    path("attendance/<uuid:session_id>/late-tap/", views.mark_late_tap, name="mark_late_tap"),
    path("attendance/<uuid:session_id>/exit/", views.mark_exit, name="mark_exit"),
    path("attendance/<uuid:session_id>/return/", views.mark_return, name="mark_return"),
    path(
        "attendance/<uuid:session_id>/late-tap/undo/",
        views.undo_late_tap_view,
        name="undo_late_tap",
    ),
    path("attendance/<uuid:session_id>/exit/cancel/", views.cancel_exit_view, name="cancel_exit"),
    path("attendance/<uuid:session_id>/complete/", views.complete_session, name="complete_session"),
    path("attendance/<uuid:session_id>/summary/", views.session_summary, name="session_summary"),
    path("reports/daily/", views.daily_report, name="daily_report"),
    # -- المرحلة 2: الجداول الذكية --
    path("weekly-schedule/", views.weekly_schedule, name="weekly_schedule"),
    path("weekly-schedule/print/", views.schedule_print, name="schedule_print"),
    path("weekly-schedule/print/view/", views.schedule_print_view, name="schedule_print_view"),
    path("weekly-schedule/export/pdf/", views.schedule_export_pdf, name="schedule_export_pdf"),
    path("weekly-schedule/pages/", views.schedule_pages, name="schedule_pages"),
    path("weekly-schedule/pages/paper/", views.schedule_pages_paper, name="schedule_pages_paper"),
    path("weekly-schedule/pages/pdf/", views.schedule_pages_pdf, name="schedule_pages_pdf"),
    path(
        "weekly-schedule/export/excel/", views.schedule_export_excel, name="schedule_export_excel"
    ),
    path(
        "weekly-schedule/export/status/<uuid:job_id>/",
        views.export_job_status,
        name="export_job_status",
    ),
    # -- المرحلة 2: نظام البديل --
    path("absences/", views.teacher_absence_list, name="absence_list"),
    path("absences/register/", views.register_teacher_absence, name="register_absence"),
    path("absences/<uuid:absence_id>/", views.absence_detail, name="absence_detail"),
    path(
        "absences/<uuid:absence_id>/assign/<uuid:slot_id>/",
        views.assign_substitute,
        name="assign_substitute",
    ),
    path(
        "absences/<uuid:absence_id>/swap/<uuid:slot_id>/",
        views.absence_swap_options,
        name="absence_swap_options",
    ),
    path(
        "absences/<uuid:absence_id>/swap/<uuid:slot_id>/create/",
        views.absence_swap_create,
        name="absence_swap_create",
    ),
    path("reports/substitutes/", views.substitute_report, name="substitute_report"),
    # -- المرحلة 3: الجدولة الذكية --
    path("smart-schedule/", views.smart_schedule_view, name="smart_schedule"),
    path("smart-schedule/generate/", views.smart_generate, name="smart_generate"),
    path("smart-schedule/status/", views.smart_generate_status, name="smart_generate_status"),
    path("smart-schedule/lab/", views.schedule_quality_lab, name="schedule_quality_lab"),
    path(
        "smart-schedule/<uuid:generation_id>/approve/",
        views.approve_schedule,
        name="approve_schedule",
    ),
    path(
        "smart-schedule/<uuid:generation_id>/discard/",
        discard_schedule,
        name="discard_schedule",
    ),
    path(
        "smart-schedule/<uuid:generation_id>/stop/",
        stop_schedule_generation,
        name="stop_schedule_generation",
    ),
    path("reports/teacher-load/", views.teacher_load_report, name="teacher_load_report"),
    path("schedule-settings/", views.schedule_settings, name="schedule_settings"),
    path("schedule-settings/exemption/grid/", views.exemption_grid, name="exemption_grid"),
    path("schedule-settings/exemption/add/", views.add_exemption, name="add_exemption"),
    path(
        "schedule-settings/exemption/<uuid:exemption_id>/remove/",
        views.remove_exemption,
        name="remove_exemption",
    ),
    path(
        "schedule-settings/exemption/remove-selected/",
        views.remove_exemptions,
        name="remove_exemptions",
    ),
    path(
        "schedule-settings/preferences/remove-selected/",
        views.remove_preferences,
        name="remove_preferences",
    ),
    path(
        "schedule-settings/subjects/save/",
        views.save_subject_scheduling,
        name="save_subject_scheduling",
    ),
    path("teacher-preferences/", views.teacher_preferences, name="teacher_preferences"),
    # ══ المرحلة 6: التبديل والتعويض ══
    path("schedule/swaps/", views.swap_list, name="swap_list"),
    path("schedule/swap/request/", views.swap_request, name="swap_request"),
    path("schedule/swap/<uuid:slot_id>/options/", views.swap_options_htmx, name="swap_options"),
    path("schedule/swap/<uuid:swap_id>/respond/", views.swap_respond, name="swap_respond"),
    path("schedule/swap/<uuid:swap_id>/approve/", views.swap_approve, name="swap_approve"),
    path("schedule/swap/<uuid:swap_id>/cancel/", views.swap_cancel, name="swap_cancel"),
    path("schedule/compensatory/", views.compensatory_list, name="compensatory_list"),
    path("schedule/compensatory/request/", views.compensatory_request, name="compensatory_request"),
    path("schedule/compensatory/options/", views.compensatory_options, name="compensatory_options"),
    path(
        "schedule/compensatory/<uuid:comp_id>/respond/",
        views.compensatory_respond,
        name="compensatory_respond",
    ),
    path(
        "schedule/compensatory/<uuid:comp_id>/approve/",
        views.compensatory_approve,
        name="compensatory_approve",
    ),
    path(
        "schedule/teacher/<uuid:teacher_id>/weekly/",
        views.teacher_weekly_view,
        name="teacher_weekly_view",
    ),
    path(
        "schedule/teacher/<uuid:teacher_id>/free-slots/",
        views.teacher_free_slots,
        name="teacher_free_slots",
    ),
    path("schedule/free-slots/build/", views.build_free_slots, name="build_free_slots"),
]
