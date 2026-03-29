from django.urls import path

from . import views

app_name = "staff_affairs"

urlpatterns = [
    # ── لوحة التحكم ──
    path("", views.staff_dashboard, name="dashboard"),

    # ── سجل الموظفين ──
    path("list/", views.staff_list, name="staff_list"),
    path("profile/<uuid:user_id>/", views.staff_profile, name="staff_profile"),

    # ── الإجازات ──
    path("leave/", views.leave_list, name="leave_list"),
    path("leave/request/", views.leave_request_create, name="leave_request"),
    path("leave/<uuid:pk>/", views.leave_detail, name="leave_detail"),
    path("leave/<uuid:pk>/review/", views.leave_review, name="leave_review"),

    # ── الرخص المهنية ──
    path("licensing/", views.licensing_overview, name="licensing"),
]
