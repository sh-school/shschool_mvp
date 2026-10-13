from django.urls import path

from . import views

app_name = "breach"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("create/", views.create, name="create"),
    path("<uuid:pk>/", views.detail, name="detail"),
    path("<uuid:pk>/edit/", views.edit, name="edit"),
    path("<uuid:pk>/status/", views.update_status, name="update_status"),
    path("<uuid:pk>/ncsa-notice/", views.ncsa_notice, name="ncsa_notice"),
    path("<uuid:pk>/ncsa-complete/", views.ncsa_complete, name="ncsa_complete"),
    path("<uuid:pk>/individuals/", views.individuals_assess, name="individuals_assess"),
    path(
        "<uuid:pk>/individuals/notified/", views.individuals_notified, name="individuals_notified"
    ),
    path("<uuid:pk>/pdf/", views.breach_pdf, name="pdf"),
]
