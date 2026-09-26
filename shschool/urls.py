from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect
from django.urls import include, path
from django.views.generic import RedirectView
from django_prometheus.exports import ExportToDjangoView

from core import views_styleguide
from core.mfa_session import admin_login_redirect
from core.permissions import internal_only
from core.views_health import (
    health_check,
    readiness_check,
    status_check,
    worker_heartbeat_check,
)
from core.views_pwa import global_manifest, global_sw, offline_global
from core.views_search import global_search
from governance.views_media import serve_db_file

urlpatterns = [
    path("health/", health_check),
    path("health/worker/", worker_heartbeat_check, name="worker_heartbeat_check"),
    # ✅ v5.4: Readiness Probe خفيف (DB فقط) — load balancer + rolling deployments
    path("ready/", readiness_check, name="readiness_check"),
    # ✅ v5.4: Full status endpoint — DB + Redis + migrations + uptime + version
    # داخليٌّ فقط (P4-9): تفاصيلُ الاتّصال وزمنُ الاستجابة لفريق العمليّات لا
    # لأيّ زائر — internal_only تحرسه كما تحرس /metrics.
    path("status/", internal_only(status_check), name="status_check"),
    path("", lambda r: redirect("dashboard/")),
    # خدمة الملفات المُخزَّنة في قاعدة البيانات (DatabaseStorage) — محمية بتسجيل الدخول
    path("dbmedia/<path:name>", serve_db_file, name="serve_db_file"),
    # قبل admin.site.urls: نموذجُ دخول Django يتخطّى الرمزَ وقفلَ المحاولات (P1-4)
    path("admin/login/", admin_login_redirect, name="admin_login_redirect"),
    path("admin/", admin.site.urls),
    path("auth/", include("core.urls.auth")),
    path("dashboard/", include("core.urls.dashboard")),
    path("core/", include("core.urls.audit")),
    path("core/it-admin/", include("core.urls.it_admin")),
    path("core/students/import-export/", include("core.urls.students")),
    path("exports/", include("core.urls.exports")),
    path("teacher/", include("operations.urls")),
    path("quality/", include("quality.urls")),
    path("assessments/", include("assessments.urls")),
    path("import/", include("staging.urls")),
    path("parents/", include("parents.urls")),
    path("reports/", include("reports.urls")),
    path("analytics/", include("analytics.urls")),
    path("notifications/", include("notifications.urls")),
    path("clinic/", include("clinic.urls")),
    path("transport/", include("transport.urls")),
    path("behavior/", include("behavior.urls")),
    path("library/", include("library.urls")),
    path("api/", include("operations.api_urls")),
    path("api/v1/", include("api.urls", namespace="api_v1")),
    # ✅ v5: وحدة كنترول الاختبارات
    path("exam-control/", include("exam_control.urls", namespace="exam_control")),
    # ✅ v5: خرق البيانات PDPPL 72h
    path("breach/", include("breach.urls", namespace="breach")),
    # ✅ v7: شؤون الطلاب
    path("student-affairs/", include("student_affairs.urls", namespace="student_affairs")),
    path("student-info/", include("student_info.urls", namespace="student_info")),
    path("wings/", include("wings.urls", namespace="wings")),
    # ✅ v7: شؤون الموظفين
    path("staff-affairs/", include("staff_affairs.urls", namespace="staff_affairs")),
    # ✅ REQ-SH-002: إدارة الشؤون الأكاديمية (Client #001) — stub phase
    path(
        "academic/",
        include("academic_management.urls", namespace="academic_management"),
    ),
    # Developer Feedback — SPRINT-DF-001 — MTG-2026-014/015/016/017/018
    path("developer-feedback/", include("developer_feedback.urls")),
    # خارطة تجويد المنصّة — لمطوّر المنصّة وحدَه (تحت «دليل الهويّة» في أدوات المطوّر)
    path("roadmap/", include("roadmap.urls")),
    # مركز قيادة الجودة — صفحةٌ في المنصّة لمطوّرها وحدَه، بجانب خارطة التجويد (QCC-01b: لا في /admin/)
    path("command-center/", include("command_center.urls")),
    # ✅ v5.1.1: Prometheus metrics — محمي بمصادقة staff + IP داخلي فقط
    path(
        "metrics",
        internal_only(staff_member_required(ExportToDjangoView)),
        name="prometheus-metrics",
    ),
    path("search/", global_search, name="global_search"),
    # دليلُ الهويّة الواحد — للمطوّرين. و`styleguide/` كان الدليلَ القديم (v5.1.1)
    # بألوانٍ منسوخةٍ وأصنافٍ بلا تعريف؛ صار تحويلاً دائماً فلا تنكسر إشارةٌ محفوظة.
    path(
        "styleguide/",
        RedirectView.as_view(pattern_name="ui_components", permanent=True),
        name="styleguide",
    ),
    path("styleguide/components/", views_styleguide.ui_components, name="ui_components"),
    path("styleguide/icons/", views_styleguide.icon_preview, name="icon_preview"),
    path("styleguide/layouts/", views_styleguide.ui_layouts, name="ui_layouts"),
    path("sw.js", global_sw, name="global_sw"),
    path("manifest.json", global_manifest, name="global_manifest"),
    path("offline/", offline_global, name="offline_global"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    # ✅ v5.1.1: Django Debug Toolbar
    try:
        import debug_toolbar

        urlpatterns += [path("__debug__/", include(debug_toolbar.urls))]
    except ImportError:
        pass
