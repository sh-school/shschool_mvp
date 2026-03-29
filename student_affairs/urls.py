from django.urls import path

from . import views

app_name = "student_affairs"

urlpatterns = [
    # ── لوحة التحكم ──
    path("", views.student_dashboard, name="dashboard"),

    # ── سجل الطلاب ──
    path("list/", views.student_list, name="student_list"),
    path("add/", views.student_add, name="student_add"),
    path("profile/<uuid:student_id>/", views.student_profile, name="student_profile"),
    path("edit/<uuid:student_id>/", views.student_edit, name="student_edit"),
    path("deactivate/<uuid:student_id>/", views.student_deactivate, name="student_deactivate"),

    # ── الانتقالات ──
    path("transfers/", views.transfer_list, name="transfer_list"),
    path("transfers/create/", views.transfer_create, name="transfer_create"),
    path("transfers/<uuid:pk>/", views.transfer_detail, name="transfer_detail"),
    path("transfers/<uuid:pk>/review/", views.transfer_review, name="transfer_review"),

    # ── الحضور والسلوك (ملخصات) ──
    path("attendance/", views.attendance_overview, name="attendance_overview"),
    path("behavior/", views.behavior_overview, name="behavior_overview"),

    # ── الأنشطة والإنجازات ──
    path("activities/", views.activity_list, name="activity_list"),
    path("activities/add/", views.activity_add, name="activity_add"),
    path("activities/<uuid:pk>/edit/", views.activity_edit, name="activity_edit"),
    path("activities/<uuid:pk>/delete/", views.activity_delete, name="activity_delete"),

    # ── HTMX Partials ──
    path("_partials/student-table/", views.student_table_partial, name="student_table_partial"),
]
