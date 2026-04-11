"""URLs لتطبيق developer_feedback."""

from django.urls import path

from developer_feedback import views

app_name = "developer_feedback"

urlpatterns = [
    path("onboarding/", views.OnboardingView.as_view(), name="onboarding"),
    path("send/", views.DeveloperMessageCreateView.as_view(), name="message_create"),
    path("success/", views.MessageSuccessView.as_view(), name="message_success"),
    path("my-messages/", views.UserMessageHistoryView.as_view(), name="my_messages"),
    path("inbox/", views.DeveloperInboxListView.as_view(), name="inbox_list"),
    path(
        "inbox/<int:pk>/",
        views.DeveloperInboxDetailView.as_view(),
        name="inbox_detail",
    ),
]
