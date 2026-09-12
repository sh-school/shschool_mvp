from django.urls import path

from . import views

app_name = "wings"

urlpatterns = [
    path("", views.floors, name="floors"),
]
