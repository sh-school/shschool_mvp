"""
Permission mixins لميزة Developer Feedback.

- NotStudentMixin: يحجب role=Student كلياً (E1 + PDPPL مادة 16)
- OnboardingRequiredMixin: يتطلب موافقة قانونية + اختبار مُنجز
- DeveloperOnlyMixin: يتيح الوصول للمطوّر/superuser فقط (Inbox)
"""

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

# ═══════════════════════════════════════════════════════════════
# NotStudentMixin
# ═══════════════════════════════════════════════════════════════


class NotStudentMixin(LoginRequiredMixin, UserPassesTestMixin):
    """يمنع الوصول إذا كان دور المستخدم = Student.

    E1 decision (MTG-2026-015): حجب كامل للطلاب القاصرين
    تحت PDPPL مادة 16.
    """

    login_url = "/accounts/login/"
    permission_denied_message = _("هذه الميزة غير متاحة لحساب الطالب.")

    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False

        # اكتشاف الدور من طرق متعددة حسب نموذج core.CustomUser
        role = (
            getattr(user, "role", None)
            or getattr(user, "user_type", None)
            or (getattr(user, "profile", None) and getattr(user.profile, "role", None))
        )
        if role and str(role).lower() in {"student", "طالب", "pupil"}:
            return False

        # Fallback: إذا كان المستخدم في مجموعة "Students"
        if user.groups.filter(name__iexact="students").exists():
            return False

        return True

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied(self.permission_denied_message)
        return super().handle_no_permission()


# ═══════════════════════════════════════════════════════════════
# OnboardingRequiredMixin
# ═══════════════════════════════════════════════════════════════


class OnboardingRequiredMixin(NotStudentMixin):
    """يشترط إتمام الإعداد القانوني قبل استخدام الميزة.

    E1 escalation #2: Onboarding قانوني 3 دقائق + اختبار + تفويض إداري.
    """

    onboarding_url = reverse_lazy("developer_feedback:onboarding")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and self.test_func():
            from developer_feedback.models import LegalOnboardingConsent

            consent = LegalOnboardingConsent.objects.filter(
                user=request.user,
                revoked_at__isnull=True,
                quiz_passed=True,
            ).first()
            if not consent:
                return redirect(self.onboarding_url)
        return super().dispatch(request, *args, **kwargs)


# ═══════════════════════════════════════════════════════════════
# DeveloperOnlyMixin
# ═══════════════════════════════════════════════════════════════


class DeveloperOnlyMixin(LoginRequiredMixin, UserPassesTestMixin):
    """يتيح الوصول للمطوّر/superuser فقط (للوصول إلى Inbox).

    إدارة: superuser أو عضو مجموعة Developers.
    """

    login_url = "/accounts/login/"

    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return user.groups.filter(name__iexact="developers").exists()
