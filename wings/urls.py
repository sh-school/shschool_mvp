from django.urls import path

from . import views, views_absence_file, views_register

app_name = "wings"

urlpatterns = [
    path("", views.floors, name="floors"),
    path("coverage/", views.coverage, name="coverage"),
    path("coverage/<slug:code>/assign/", views.coverage_assign, name="coverage_assign"),
    path("coverage/<uuid:pk>/end/", views.coverage_end, name="coverage_end"),
    path("record/", views.record_index, name="record_index"),
    path("record/<uuid:class_id>/", views.record_section, name="record_section"),
    path("record/<uuid:class_id>/period/", views.record_period, name="record_period"),
    path(
        "record/<uuid:class_id>/student/<uuid:student_id>/",
        views.student_events,
        name="student_events",
    ),
    path(
        "record/event/<uuid:pk>/delete/",
        views.attendance_event_delete,
        name="attendance_event_delete",
    ),
    path("record/exit/<uuid:pk>/delete/", views.exit_event_delete, name="exit_event_delete"),
    path(
        "record/<uuid:class_id>/student/<uuid:student_id>/excuse/",
        views.excuse_grant,
        name="excuse_grant",
    ),
    path("record/excuse/<uuid:pk>/revoke/", views.excuse_revoke, name="excuse_revoke"),
    path("students/find/", views_absence_file.student_search, name="student_search"),
    path(
        "students/<uuid:student_id>/absences/",
        views_absence_file.absence_file,
        name="absence_file",
    ),
    path(
        "students/<uuid:student_id>/absences/excuse/",
        views_absence_file.absence_file_excuse,
        name="absence_file_excuse",
    ),
    path(
        "students/<uuid:student_id>/absences/contact/",
        views_absence_file.absence_file_contact,
        name="absence_file_contact",
    ),
    path("excuses/requests/", views.excuse_requests, name="excuse_requests"),
    path(
        "excuses/requests/<uuid:pk>/decide/",
        views.excuse_request_decide,
        name="excuse_request_decide",
    ),
    path(
        "record/<uuid:class_id>/student/<uuid:student_id>/contact/",
        views.guardian_contact_log,
        name="guardian_contact_log",
    ),
    path(
        "record/<uuid:class_id>/register/",
        views_register.section_register_export,
        name="section_register",
    ),
    path(
        "record/wing/<slug:code>/register/",
        views_register.wing_register_export,
        name="wing_register",
    ),
]
