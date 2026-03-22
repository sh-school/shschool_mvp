from django.urls import path

from . import api_views

urlpatterns = [
    path("sessions/", api_views.SessionListView.as_view(), name="api_sessions"),
    path("attendance/", api_views.AttendanceListView.as_view(), name="api_attendance"),
    path("students/search/", api_views.student_search_api, name="api_student_search"),
]
