from django.urls import path

from core.views_dashboard import dashboard

urlpatterns = [
    path("", dashboard, name="dashboard"),
]
