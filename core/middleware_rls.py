"""
core/middleware_rls.py
━━━━━━━━━━━━━━━━━━━━━
PostgreSQL Row-Level Security Middleware.
يضبط متغير الاتصال app.current_school_id لكل طلب (fail-closed).
[SEC-07] المتغيّر بيانات وصفية للتطبيق — هوية المستأجر في RLS تأتي من دور
الاتصال منذ migration 0037، لا من هذا المتغيّر.
"""

import logging

import django.db
from django.db import connection

logger = logging.getLogger("core")


class RLSMiddleware:
    """
    يضبط app.current_school_id على اتصال PostgreSQL لكل طلب — **كبيانات وصفية
    للتطبيق، لا كمصدر لهوية المستأجر**.

    [SEC-07] هذا المتغيّر لم يعد جزءاً من قرار RLS الأمني. منذ migration 0037
    تشتقّ سياسات school_isolation الهوية من دور الاتصال:
        app_rls_school() ← app_rls_role_school ← session_user
    أي من اعتماد قاعدة البيانات، وهو ما لا يستطيع الـSQL المحقون تغييره.

    السبب: المتغيّرات المخصّصة يضبطها أي دور بلا صلاحية، فكان الطرف الذي تحكمه
    السياسة هو من يُعرّف هويته فيها. قياساً على مخطّط التطوير بدور shschool_app،
    كان ضبط UUID مدرسة أخرى يكشف صفوفها كاملةً.

    القيمة المضبوطة:
      - <school_uuid>  لكل مستخدم مُعتمَد له عضوية
      - ''             لغير المُعتمَد / بلا عضوية

    ولا يوجد تجاوز على مستوى الطلب — ولا حتى للـ superuser: يُحلّ عبر عضويته
    كأي مستخدم، ومن لا عضوية له لا يرى صفوفاً على الجداول المحميّة.

    يُضبط بـ is_local=False ليدوم عبر كل استعلامات الطلب دون الاعتماد على
    ATOMIC_REQUESTS، ويُعاد تعيينه في finally ويُضبط من جديد في بداية كل طلب
    لمنع تسرّب السياق عبر الاتصالات المُجمّعة (CONN_MAX_AGE).

    [SEC-01] fail-closed: إن تعذّر ضبط السياق (خطأ قاعدة بيانات) نرفض الطلب بـ 503
    بدل المتابعة بسياق موروث من طلب سابق على نفس الاتصال المُجمّع — إغلاق نافذة
    تسرّب البيانات عبر المستأجرين.

    يجب أن يعمل بعد AuthenticationMiddleware وقبل أي middleware يستعلم جداول
    محميّة (SchoolPermissionMiddleware / SessionAutoGenerateMiddleware ...).
    يعمل بالتنسيق مع migration 0033_rls_hardening.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            self._apply(self._context(request))
        except (django.db.OperationalError, django.db.DatabaseError) as e:
            logger.error("RLS context set FAILED — رفض الطلب (fail-closed): %s", e)
            from django.http import HttpResponse

            return HttpResponse("الخدمة غير متاحة مؤقتاً", status=503)
        try:
            return self.get_response(request)
        finally:
            # إعادة التعيين حتى لا يتسرّب السياق للطلب التالي على نفس الاتصال
            try:
                self._apply("")
            except (django.db.OperationalError, django.db.DatabaseError) as e:
                logger.warning("RLS context reset failed: %s", e)

    def _context(self, request):
        """
        يحسب قيمة السياق من المستخدم المُعتمَد.

        [SEC-05] لا استثناء للـ superuser — العضوية هي المصدر الوحيد للسياق.
        """
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return ""
        try:
            school = user.get_school()
        except AttributeError:
            return ""
        if school:
            return str(school.pk)
        if user.is_superuser:
            # تشخيص: superuser بلا عضوية لن يرى صفوفاً على الجداول المحميّة.
            logger.warning(
                "RLS: superuser id=%s بلا عضوية مدرسة — سياق فارغ (لا صفوف).",
                user.pk,
            )
        return ""

    def _apply(self, value):
        """
        ضبط متغير الاتصال في PostgreSQL (session-level).
        fail-closed: يرفع الاستثناء عند الفشل ليُعالَج في __call__.
        الاختبارات/قواعد غير PostgreSQL لا تدعم set_config — تخطٍّ آمن.
        """
        if connection.vendor != "postgresql":
            return
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.current_school_id', %s, false)",
                [value],
            )
