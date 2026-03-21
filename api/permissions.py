"""
api/permissions.py
صلاحيات REST API المخصصة
"""
from rest_framework.permissions import BasePermission


class IsSchoolAdmin(BasePermission):
    """مدير المدرسة أو superuser"""
    message = "هذا الطلب للمديرين فقط."

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (request.user.is_admin() or request.user.is_superuser)
        )


class IsTeacherOrAdmin(BasePermission):
    """معلم أو مدير"""
    message = "هذا الطلب للمعلمين والمديرين فقط."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.is_admin() or request.user.has_role("teacher")


class IsParentOrAdmin(BasePermission):
    """ولي أمر أو مدير"""
    message = "هذا الطلب لأولياء الأمور والمديرين فقط."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return (
            request.user.is_admin() or
            request.user.is_superuser or
            request.user.has_role("parent")
        )
