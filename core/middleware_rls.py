"""
core/middleware_rls.py
━━━━━━━━━━━━━━━━━━━━━
PostgreSQL Row-Level Security Middleware.
يضبط متغير الاتصال app.current_school_id لتفعيل سياسات RLS (fail-closed).
"""

import logging

import django.db
from django.db import connection

logger = logging.getLogger("core")


class RLSMiddleware:
    """
    يضبط app.current_school_id على اتصال PostgreSQL لكل طلب لتفعيل سياسات RLS.

    القيمة المضبوطة:
      - '*'           للـ superuser (يرى كل المدارس — تجاوز منضبط)
      - <school_uuid>  للمستخدم العادي (يرى مدرسته فقط)
      - ''             لغير المُعتمَد / بلا مدرسة ⇒ لا صفوف على الجداول المحميّة

    يُضبط بـ is_local=False ليدوم عبر كل استعلامات الطلب دون الاعتماد على
    ATOMIC_REQUESTS، ويُعاد تعيينه في finally ويُضبط من جديد في بداية كل طلب
    لمنع تسرّب السياق عبر الاتصالات المُجمّعة (CONN_MAX_AGE).

    يجب أن يعمل بعد AuthenticationMiddleware وقبل أي middleware يستعلم جداول
    محميّة (SchoolPermissionMiddleware / SessionAutoGenerateMiddleware ...).
    يعمل بالتنسيق مع migration 0033_rls_hardening.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        self._apply(self._context(request))
        try:
            return self.get_response(request)
        finally:
            # إعادة التعيين حتى لا يتسرّب السياق للطلب التالي على نفس الاتصال
            self._apply("")

    def _context(self, request):
        """يحسب قيمة السياق من المستخدم المُعتمَد."""
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return ""
        if user.is_superuser:
            return "*"
        try:
            school = user.get_school()
        except AttributeError:
            return ""
        return str(school.pk) if school else ""

    def _apply(self, value):
        """ضبط متغير الاتصال في PostgreSQL (session-level)."""
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('app.current_school_id', %s, false)",
                    [value],
                )
        except (django.db.OperationalError, django.db.DatabaseError) as e:
            logger.warning("RLS context set failed: %s", e)
