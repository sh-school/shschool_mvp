from django.urls import path

from . import views

app_name = "student_info"

urlpatterns = [
    path("", views.sections, name="sections"),
    path("section/<uuid:class_id>/", views.section_students, name="section_students"),
    path("student/<uuid:student_id>/", views.student_file, name="student_file"),
    path("student/<uuid:student_id>/note/new/", views.note_create, name="note_create"),
    path("levels/", views.levels, name="levels"),
    path("notes/<str:category>/", views.notes, name="notes"),
    path("activities/", views.activities, name="activities"),
]
