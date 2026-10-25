from django.urls import path

from ux_survey import views

app_name = "ux_survey"

urlpatterns = [
    path("respond/", views.respond, name="respond"),
    path("snooze/", views.snooze, name="snooze"),
    path("close/", views.close, name="close"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("review/", views.review, name="review"),
]
