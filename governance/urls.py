"""مساراتُ شاشة طلبات محو بيانات الطالب (PDPPL م.18)."""

from django.urls import path

from governance import views_erasure

urlpatterns = [
    path("", views_erasure.erasure_requests, name="erasure_requests"),
    path("officer/", views_erasure.erasure_assign_officer, name="erasure_assign_officer"),
    path("<uuid:request_id>/sign/", views_erasure.erasure_sign, name="erasure_sign"),
    path("<uuid:request_id>/reject/", views_erasure.erasure_reject, name="erasure_reject"),
]
