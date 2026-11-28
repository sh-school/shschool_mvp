from django.urls import path

from governance import views_erasure

app_name = "governance"

urlpatterns = [
    path("erasure/", views_erasure.erasure_requests, name="erasure_requests"),
    path("erasure/officer/", views_erasure.erasure_appoint_officer, name="erasure_officer"),
    path("erasure/<uuid:request_id>/sign/", views_erasure.erasure_sign, name="erasure_sign"),
    path("erasure/<uuid:request_id>/reject/", views_erasure.erasure_reject, name="erasure_reject"),
]
