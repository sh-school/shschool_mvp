from django.urls import path

from core.views_audit import permission_audit_log

urlpatterns = [
    path("permission-audit/", permission_audit_log, name="permission_audit_log"),
]
