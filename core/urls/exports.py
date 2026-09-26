"""مساراتُ التصدير المركزيّة — الحالةُ والتنزيلُ وصفحةُ المتابعة (`core.exports`)."""

from django.urls import path

from core.exports import views

urlpatterns = [
    path("<uuid:job_id>/", views.export_page, name="export_page"),
    path("<uuid:job_id>/status/", views.export_status, name="export_status"),
    path("<uuid:job_id>/download/", views.export_download, name="export_download"),
]
