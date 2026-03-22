"""
api/urls.py
━━━━━━━━━━
SchoolOS REST API v1 — نقاط النهاية

/api/v1/schema/          OpenAPI schema (YAML/JSON)
/api/v1/docs/            Swagger UI
/api/v1/redoc/           ReDoc
/api/v1/auth/token/      JWT Login
/api/v1/auth/token/refresh/ JWT Refresh
"""
from django.urls import path
from drf_spectacular.views import (
    SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView,
)
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from . import views
from . import views_erasure

app_name = "api_v1"

urlpatterns = [

    # ── OpenAPI Documentation ────────────────────────────────────
    path("schema/",  SpectacularAPIView.as_view(),              name="schema"),
    path("docs/",    SpectacularSwaggerView.as_view(url_name="api_v1:schema"), name="swagger-ui"),
    path("redoc/",   SpectacularRedocView.as_view(url_name="api_v1:schema"),   name="redoc"),

    # ── JWT Auth (للتطبيق المحمول المستقبلي) ─────────────────────
    path("auth/token/",         TokenObtainPairView.as_view(),  name="token_obtain"),
    path("auth/token/refresh/", TokenRefreshView.as_view(),     name="token_refresh"),

    # ── Me ────────────────────────────────────────────────────────
    path("me/", views.me_view, name="me"),

    # ── Students ─────────────────────────────────────────────────
    path("students/",                              views.student_list,       name="student-list"),
    path("students/<uuid:student_id>/grades/",     views.student_grades,     name="student-grades"),
    path("students/<uuid:student_id>/attendance/", views.student_attendance, name="student-attendance"),

    # ── Classes ──────────────────────────────────────────────────
    path("classes/",                           views.class_list,    name="class-list"),
    path("classes/<uuid:class_id>/results/",   views.class_results, name="class-results"),

    # ── Sessions & Attendance ─────────────────────────────────────
    path("sessions/",    views.SessionListView.as_view(),    name="session-list"),
    path("attendance/",  views.AttendanceListView.as_view(), name="attendance-list"),

    # ── Behavior ─────────────────────────────────────────────────
    path("behavior/", views.behavior_list, name="behavior-list"),

    # ── Notifications ─────────────────────────────────────────────
    path("notifications/",                                 views.notification_list,         name="notification-list"),
    path("notifications/mark-all-read/",                   views.notification_mark_all_read, name="notification-mark-all"),
    path("notifications/<uuid:notif_id>/read/",            views.notification_mark_read,     name="notification-read"),
    path("notification-preferences/",                      views.NotificationPreferencesView.as_view(), name="notif-prefs"),

    # ── KPIs ──────────────────────────────────────────────────────
    path("kpis/", views.kpi_list, name="kpi-list"),

    # ── Parent Portal ─────────────────────────────────────────────
    path("parent/children/",                                   views.parent_children,          name="parent-children"),
    path("parent/children/<uuid:student_id>/grades/",          views.parent_child_grades,      name="parent-child-grades"),
    path("parent/children/<uuid:student_id>/attendance/",      views.parent_child_attendance,  name="parent-child-attendance"),

    # ── Library ───────────────────────────────────────────────────
    path("library/books/",      views.LibraryBookListView.as_view(),  name="library-books"),
    path("library/borrowings/", views.BorrowingListView.as_view(),    name="library-borrowings"),

    # ── Clinic ────────────────────────────────────────────────────
    path("clinic/visits/", views.ClinicVisitListView.as_view(), name="clinic-visits"),

    # ── PDPPL Right to Erasure (م.18) ─────────────────────────────
    path("erasure/request/",                          views_erasure.create_erasure_request,  name="erasure-create"),
    path("erasure/requests/",                         views_erasure.list_erasure_requests,   name="erasure-list"),
    path("erasure/requests/<uuid:request_id>/",       views_erasure.erasure_request_detail,  name="erasure-detail"),
    path("erasure/requests/<uuid:request_id>/approve/", views_erasure.approve_erasure,       name="erasure-approve"),
    path("erasure/requests/<uuid:request_id>/reject/",  views_erasure.reject_erasure,        name="erasure-reject"),
]
