from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect

urlpatterns = [
    path("",               lambda r: redirect("dashboard/")),
    path("admin/",         admin.site.urls),
    path("auth/",          include("core.urls.auth")),
    path("dashboard/",     include("core.urls.dashboard")),
    path("teacher/",       include("operations.urls")),
    path("quality/",       include("quality.urls")),
    path("assessments/",   include("assessments.urls")),
    path("import/",        include("staging.urls")),
    path("parents/",       include("parents.urls")),
    path("reports/",       include("reports.urls")),
    path("analytics/",     include("analytics.urls")),
    path("notifications/", include("notifications.urls")),
    path("clinic/",        include("clinic.urls")),
    path("transport/",     include("transport.urls")),
    path("behavior/",      include("behavior.urls")),
    path("library/",       include("library.urls")),
    path("api/",           include("operations.api_urls")),
    # ✅ v5: وحدة كنترول الاختبارات
    path("exam-control/",  include("exam_control.urls", namespace="exam_control")),
    # ✅ v5: خرق البيانات PDPPL 72h
    path("breach/",        include("breach.urls", namespace="breach")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,  document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
