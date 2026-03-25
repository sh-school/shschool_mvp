"""
core/middleware_rls.py
━━━━━━━━━━━━━━━━━━━━━
PostgreSQL Row-Level Security Middleware.
يضبط متغير الجلسة app.current_school_id لتفعيل سياسات RLS.
"""

import logging

from django.db import connection

logger = logging.getLogger("core")


class RLSMiddleware:
    """
    يضبط SET LOCAL app.current_school_id = '<school_uuid>'
    في بداية كل طلب HTTP مُعتمَد.

    هذا يُفعّل سياسات PostgreSQL RLS التي تمنع تسرب البيانات
    بين المدارس على مستوى قاعدة البيانات.

    يعمل بالتنسيق مع:
    - Migration 0021_postgresql_rls_policies.py
    - SchoolPermissionMiddleware (يحدد المدرسة النشطة)
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        school_id = self._get_school_id(request)
        if school_id:
            self._set_rls_context(school_id)

        response = self.get_response(request)
        return response

    def _get_school_id(self, request):
        """استخراج school_id من المستخدم المُعتمَد."""
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            try:
                school = user.get_school()
                if school:
                    return str(school.pk)
            except Exception:
                pass
        return None

    def _set_rls_context(self, school_id):
        """ضبط متغير الجلسة في PostgreSQL."""
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('app.current_school_id', %s, true)",
                    [school_id],
                )
        except Exception as e:
            logger.warning("RLS context set failed: %s", e)
