from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path

from core.views_health import health_check
from core.views_pwa import global_sw, global_manifest, offline_global
from core.views_search import global_search

urlpatterns = [
    path("health/", health_check),
    path("", lambda r: redirect("dashboard/")),
    path("admin/", admin.site.urls),
    path("auth/", include("core.urls.auth")),
    path("dashboard/", include("core.urls.dashboard")),
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
    # ✅ v5.1: Prometheus metrics — /metrics/ (محمي بـ firewall/VPN في الإنتاج)
    path("", include("django_prometheus.urls")),
    path("search/", global_search, name="global_search"),
    path('sw.js', global_sw, name='global_sw'),
    path('manifest.json', global_manifest, name='global_manifest'),
    path('offline/', offline_global, name='offline_global'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
