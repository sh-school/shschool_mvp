from django.urls import path

from . import views

urlpatterns = [
    path("schedule/", views.schedule, name="teacher_schedule"),
    path("attendance/<uuid:session_id>/", views.attendance_view, name="attendance"),
    path("attendance/<uuid:session_id>/mark-single/", views.mark_single, name="mark_single"),
    path("attendance/<uuid:session_id>/mark-all/", views.mark_all_present, name="mark_all_present"),
    path("attendance/<uuid:session_id>/complete/", views.complete_session, name="complete_session"),
    path("attendance/<uuid:session_id>/summary/", views.session_summary, name="session_summary"),
    path("reports/daily/", views.daily_report, name="daily_report"),
    # -- المرحلة 2: الجداول الذكية --
    path("weekly-schedule/", views.weekly_schedule, name="weekly_schedule"),
    path("weekly-schedule/print/", views.schedule_print, name="schedule_print"),
    path("weekly-schedule/add/", views.schedule_slot_create, name="slot_create"),
    path("weekly-schedule/delete/<uuid:slot_id>/", views.schedule_slot_delete, name="slot_delete"),
    path("weekly-schedule/generate/", views.generate_sessions, name="generate_sessions"),
    # -- المرحلة 2: نظام البديل --
    path("absences/", views.teacher_absence_list, name="absence_list"),
    path("absences/register/", views.register_teacher_absence, name="register_absence"),
    path("absences/<uuid:absence_id>/", views.absence_detail, name="absence_detail"),
    path(
        "absences/<uuid:absence_id>/assign/<uuid:slot_id>/",
        views.assign_substitute,
        name="assign_substitute",
    ),
    path("reports/substitutes/", views.substitute_report, name="substitute_report"),
    # -- المرحلة 3: الجدولة الذكية --
    path("smart-schedule/", views.smart_schedule_view, name="smart_schedule"),
    path("smart-schedule/generate/", views.smart_generate, name="smart_generate"),
    path(
        "smart-schedule/<uuid:generation_id>/approve/",
        views.approve_schedule,
        name="approve_schedule",
    ),
    path("reports/teacher-load/", views.teacher_load_report, name="teacher_load_report"),
    path("schedule-settings/", views.schedule_settings, name="schedule_settings"),
    path("schedule-settings/exemption/add/", views.add_exemption, name="add_exemption"),
    path(
        "schedule-settings/exemption/<uuid:exemption_id>/remove/",
        views.remove_exemption,
        name="remove_exemption",
    ),
    path(
        "schedule-settings/subject/<uuid:subject_id>/toggle-double/",
        views.toggle_double_period,
        name="toggle_double_period",
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
