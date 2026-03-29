from django.urls import path

from . import views

app_name = "clinic"

urlpatterns = [
    path("", views.clinic_dashboard, name="dashboard"),
    path("student/<uuid:student_id>/record/", views.student_health_record, name="health_record"),
    path("visit/new/", views.record_visit, name="record_visit"),
    path("visit/new/<uuid:student_id>/", views.record_visit, name="record_visit_student"),
    path("visits/", views.visits_list, name="visits_list"),
    path("statistics/", views.health_statistics, name="statistics"),
    path("api/charts/", views.api_clinic_charts, name="api_clinic_charts"),
]
