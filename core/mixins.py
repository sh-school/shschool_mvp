"""
core/mixins.py
━━━━━━━━━━━━━━
View-level mixins لحماية Multi-Tenancy.

SchoolScopedMixin:
  يتحقق أن المستخدم ينتمي لنفس المدرسة التي يحاول الوصول إليها.
  يمنع تسرب البيانات بين المدارس على مستوى العرض (Defense in Depth).
"""

import logging

from django.core.exceptions import PermissionDenied

logger = logging.getLogger(__name__)


class SchoolScopedMixin:
    """
    View Mixin — يتحقق من تطابق مدرسة المستخدم مع مدرسة الطلب.

    يعمل بالتنسيق مع:
      - RLSMiddleware (حماية على مستوى قاعدة البيانات)
      - SchoolPermissionMiddleware (حماية على مستوى المسارات)

    الاستخدام:
        class MyView(SchoolScopedMixin, View):
            def get(self, request, *args, **kwargs):
                ...

    يدعم حالتين:
      1. request.school موجود (إذا أُضيف بواسطة middleware مستقبلاً)
      2. fallback: يستخدم user.get_school() مع التحقق من staff.school_id
    """

    def dispatch(self, request, *args, **kwargs):
        # Superusers تمر بدون تقييد
        if request.user.is_authenticated and request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)

        if hasattr(request, "school") and request.user.is_authenticated:
            # الحالة 1: middleware يضع request.school
            user_school = request.user.get_school()
            if user_school and user_school.pk != request.school.pk:
                logger.warning(
                    "SchoolScopedMixin: school mismatch — user %s (school=%s) "
                    "tried to access school=%s",
                    request.user.pk,
                    user_school.pk,
                    request.school.pk,
                )
                raise PermissionDenied("School mismatch — ليس لديك صلاحية الوصول لهذه المدرسة")

        elif request.user.is_authenticated:
            # الحالة 2: التحقق عبر user.get_school()
            user_school = request.user.get_school()
            if not user_school:
                logger.warning(
                    "SchoolScopedMixin: user %s has no school assigned",
                    request.user.pk,
                )
                raise PermissionDenied("لم يتم تعيين مدرسة لحسابك — تواصل مع مدير النظام")

            # حفظ المدرسة على request للاستخدام في views الفرعية
            request.school = user_school

        return super().dispatch(request, *args, **kwargs)
