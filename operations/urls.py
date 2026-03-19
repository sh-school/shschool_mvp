from django.urls import path
from . import views

urlpatterns = [
    path("schedule/",                         views.schedule,        name="teacher_schedule"),
    path("attendance/<uuid:session_id>/",     views.attendance_view, name="attendance"),
    path("attendance/<uuid:session_id>/mark-single/", views.mark_single,    name="mark_single"),
    path("attendance/<uuid:session_id>/mark-all/",    views.mark_all_present, name="mark_all_present"),
    path("attendance/<uuid:session_id>/complete/",    views.complete_session, name="complete_session"),
    path("attendance/<uuid:session_id>/summary/",     views.session_summary,  name="session_summary"),
    path("reports/daily/",                    views.daily_report,    name="daily_report"),

    # ── المرحلة 2: الجداول الذكية ──
    path("weekly-schedule/",                  views.weekly_schedule,      name="weekly_schedule"),
    path("weekly-schedule/add/",              views.schedule_slot_create, name="slot_create"),
    path("weekly-schedule/delete/<uuid:slot_id>/", views.schedule_slot_delete, name="slot_delete"),
    path("weekly-schedule/generate/",         views.generate_sessions,    name="generate_sessions"),

    # ── المرحلة 2: نظام البديل ──
    path("absences/",                         views.teacher_absence_list,    name="absence_list"),
    path("absences/register/",                views.register_teacher_absence,name="register_absence"),
    path("absences/<uuid:absence_id>/",       views.absence_detail,          name="absence_detail"),
    path("absences/<uuid:absence_id>/assign/<uuid:slot_id>/",
                                              views.assign_substitute,       name="assign_substitute"),
    path("reports/substitutes/",              views.substitute_report,       name="substitute_report"),
]
