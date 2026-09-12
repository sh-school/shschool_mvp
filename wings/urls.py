from django.urls import path

from . import views

app_name = "wings"

urlpatterns = [
    path("", views.floors, name="floors"),
    path("coverage/", views.coverage, name="coverage"),
    path("coverage/<slug:code>/assign/", views.coverage_assign, name="coverage_assign"),
    path("coverage/<uuid:pk>/end/", views.coverage_end, name="coverage_end"),
    path("record/", views.record_index, name="record_index"),
    path("record/<uuid:class_id>/", views.record_section, name="record_section"),
]
