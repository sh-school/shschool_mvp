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
      - <school_uuid>  لكل مستخدم مُعتمَد له عضوية (يرى مدرسته فقط)
      - ''             لغير المُعتمَد / بلا عضوية ⇒ لا صفوف على الجداول المحميّة

    [SEC-05] لا يوجد تجاوز على مستوى الطلب — ولا حتى للـ superuser. كان السياق '*'
    يُعطّل العزل على كل الجداول دفعةً واحدة، وهو متغيّر جلسة يستطيع أي دور ضبطه
    بلا صلاحية، فكان حقنُ جملةٍ ثانية كافياً لإلغاء العزل بالكامل. أُزيل التجاوز
    في migration 0037. الـ superuser يُحلّ الآن عبر عضويته كأي مستخدم؛ ومن لا
    عضوية له لا يرى صفوفاً على الجداول المحميّة.

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
