"""
api/permissions.py
══════════════════════════════════════════════════════════════════════
صلاحيات REST API — مبنية على نظام RBAC الموحّد
══════════════════════════════════════════════════════════════════════
"""

from rest_framework.permissions import BasePermission

from core.models.access import ADMIN_ROLES, ALL_STAFF_ROLES, LEADERSHIP


class IsSchoolAdmin(BasePermission):
    """مدير المدرسة أو superuser — صلاحيات كاملة."""

    message = "هذا الطلب للمديرين فقط."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_admin() or request.user.is_superuser)
        )


class IsLeadership(BasePermission):
    """المدير ونوابه (T1 + T2)."""

    message = "هذا الطلب للقيادة المدرسية فقط."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.is_superuser or request.user.get_role() in LEADERSHIP


class IsTeacherOrAdmin(BasePermission):
    """معلم أو مدير."""

    message = "هذا الطلب للمعلمين والمديرين فقط."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.is_admin() or request.user.get_role() in (
            "teacher", "coordinator", "ese_teacher",
        )


class IsStaffMember(BasePermission):
    """أي موظف بالمدرسة (ليس طالب أو ولي أمر)."""

    message = "هذا الطلب لموظفي المدرسة فقط."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.is_superuser or request.user.get_role() in (
            ALL_STAFF_ROLES | {"specialist"}
        )


class IsParentOrAdmin(BasePermission):
    """ولي أمر أو مدير."""

    message = "هذا الطلب لأولياء الأمور والمديرين فقط."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return (
            request.user.is_admin()
            or request.user.is_superuser
            or request.user.has_role("parent")
        )


class IsSameDepartment(BasePermission):
    """
    يتحقق من أن المستخدم من نفس القسم/التخصص.
    يتطلب أن يكون الـ view يملك `department` attribute أو kwarg.
    القيادة تمر بدون تقييد.
    """

    message = "لا يمكنك الوصول إلى بيانات قسم آخر."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser or request.user.get_role() in LEADERSHIP:
            return True

        dept = getattr(view, "department", None) or view.kwargs.get("department", "")
        if not dept:
            return True  # لا يوجد قسم محدد = السماح والتحقق في الـ view
        return request.user.department == dept
