"""URLs لتطبيق developer_feedback."""

from django.urls import path

from developer_feedback import views

app_name = "developer_feedback"

urlpatterns = [
    path("onboarding/", views.OnboardingView.as_view(), name="onboarding"),
    path("send/", views.DeveloperMessageCreateView.as_view(), name="message_create"),
    path("success/", views.MessageSuccessView.as_view(), name="message_success"),
    path("my-messages/", views.UserMessageHistoryView.as_view(), name="my_messages"),
    path(
        "my-messages/<int:pk>/edit/",
        views.DeveloperMessageEditView.as_view(),
        name="message_edit",
    ),
    path("inbox/", views.DeveloperInboxListView.as_view(), name="inbox_list"),
    path(
        "inbox/<int:pk>/",
        views.DeveloperInboxDetailView.as_view(),
        name="inbox_detail",
    ),
    # ── الاتّجاه المعاكس: المطوّر يرسل لمستخدمين (التسليمُ عبر جرس الإشعارات القائم) ──
    path("broadcast/send/", views.broadcast_create, name="broadcast_create"),
    path("broadcast/sent/", views.BroadcastSentListView.as_view(), name="broadcast_sent"),
    path(
        "broadcast/recipient-count/",
        views.broadcast_recipient_count,
        name="broadcast_recipient_count",
    ),
]
