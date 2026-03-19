from django.urls import path
from . import views

urlpatterns = [
    path("",                              views.notifications_dashboard, name="notifications_dashboard"),
    path("send/absence/",                 views.send_absence_alerts,     name="send_absence_alerts"),
    path("send/fail/",                    views.send_fail_alerts,        name="send_fail_alerts"),
    path("resend/<uuid:log_id>/",         views.resend_notification,     name="resend_notification"),
    path("settings/",                     views.save_settings,           name="save_notif_settings"),
]
