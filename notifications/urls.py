from django.urls import path

from . import views

urlpatterns = [
    # ── لوحة الإدارة (المدير) ──────────────────────────────
    path("", views.notifications_dashboard, name="notifications_dashboard"),
    path("send/absence/", views.send_absence_alerts, name="send_absence_alerts"),
    path("send/fail/", views.send_fail_alerts, name="send_fail_alerts"),
    path("resend/<uuid:log_id>/", views.resend_notification, name="resend_notification"),
    path("settings/", views.save_settings, name="save_notif_settings"),
    # ── v6: صندوق الإشعارات (كل المستخدمين) ─────────────────
    path("inbox/", views.notification_inbox, name="notification_inbox"),
    path("preferences/", views.notification_preferences, name="notification_preferences"),
    path("mark-read/<uuid:notif_id>/", views.mark_notification_read, name="mark_notification_read"),
    path("mark-all-read/", views.mark_all_read, name="mark_all_read"),
    # ── v6: APIs للجرس (HTMX / JSON) ────────────────────────
    path("api/unread-count/", views.api_unread_count, name="api_unread_count"),
    path("api/recent/", views.api_recent_notifications, name="api_recent_notifications"),
]
