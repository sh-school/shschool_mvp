from django.urls import path

from . import views

app_name = "exam_control"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("session/create/", views.session_create, name="session_create"),
    path("session/<uuid:pk>/", views.session_detail, name="session_detail"),
    path("session/<uuid:pk>/supervisors/", views.supervisors, name="supervisors"),
    path("session/<uuid:pk>/schedule/", views.schedule, name="schedule"),
    path("session/<uuid:pk>/incidents/", views.incidents, name="incidents"),
    path("session/<uuid:pk>/incident/add/", views.incident_add, name="incident_add"),
    path("incident/<uuid:pk>/pdf/", views.incident_pdf, name="incident_pdf"),
    path("session/<uuid:pk>/grade-sheets/", views.grade_sheets, name="grade_sheets"),
    path("session/<uuid:pk>/report-pdf/", views.session_report_pdf, name="session_report_pdf"),
]
