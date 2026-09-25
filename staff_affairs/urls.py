from django.urls import path

from . import views, views_attendance, views_exemptions

app_name = "staff_affairs"

urlpatterns = [
    # ── لوحة التحكم ──
    path("", views.staff_dashboard, name="dashboard"),
    # ── سجل الموظفين ──
    path("list/", views.staff_list, name="staff_list"),
    path("profile/<uuid:user_id>/", views.staff_profile, name="staff_profile"),
    # ── التعيينُ والمغادرة: قرارٌ له مرجعٌ وتاريخ ──
    path("appoint/", views.staff_appoint, name="staff_appoint"),
    path(
        "profile/<uuid:user_id>/save/<slug:section>/",
        views.staff_profile_save,
        name="staff_profile_save",
    ),
    path("profile/<uuid:user_id>/depart/", views.staff_depart, name="staff_depart"),
    path("profile/<uuid:user_id>/reinstate/", views.staff_reinstate, name="staff_reinstate"),
    # ── الإجازات ──
    path("leave/", views.leave_list, name="leave_list"),
    path("leave/request/", views.leave_request_create, name="leave_request"),
    path("leave/<uuid:pk>/", views.leave_detail, name="leave_detail"),
    path("leave/<uuid:pk>/review/", views.leave_review, name="leave_review"),
    # ── حضورُ الموظّفين (1.1) والأذونات القصيرة (1.3) ──
    path("attendance/", views_attendance.attendance_board, name="attendance_board"),
    path("attendance/mark/", views_attendance.attendance_mark, name="attendance_mark"),
    path("attendance/report/", views_attendance.attendance_report, name="attendance_report"),
    path(
        "attendance/report/xlsx/",
        views_attendance.attendance_report_xlsx,
        name="attendance_report_xlsx",
    ),
    path("permits/mine/", views_attendance.my_permits, name="my_permits"),
    path("permits/<uuid:pk>/cancel/", views_attendance.permit_cancel, name="permit_cancel"),
    path("permits/review/", views_attendance.permit_queue, name="permit_queue"),
    path("permits/<uuid:pk>/review/", views_attendance.permit_review, name="permit_review"),
    path(
        "permits/exceptions/<uuid:pk>/review/",
        views_attendance.exception_review,
        name="exception_review",
    ),
    path("assignments/", views_attendance.staff_assignments, name="assignments"),
    path(
        "assignments/<uuid:pk>/revoke/",
        views_attendance.staff_assignment_revoke,
        name="assignment_revoke",
    ),
    path("exemptions/", views_exemptions.staff_exemptions, name="exemptions"),
    path(
        "exemptions/<uuid:pk>/revoke/",
        views_exemptions.staff_exemption_revoke,
        name="exemption_revoke",
    ),
    # ── الرخص المهنية ──
    path("licensing/", views.licensing_overview, name="licensing"),
]
