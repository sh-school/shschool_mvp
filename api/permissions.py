"""
api/permissions.py
══════════════════════════════════════════════════════════════════════
صلاحيات REST API — مبنية على نظام RBAC الموحّد
══════════════════════════════════════════════════════════════════════
"""

from rest_framework.permissions import BasePermission

from core.models.access import ADMIN_ROLES, ALL_STAFF_ROLES, LEADERSHIP
from core.models import ParentStudentLink


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
    """ولي أمر أو مدير.

    SECURITY NOTE:
    للـ @api_view (FBVs)، DRF لا يستدعي has_object_permission تلقائياً.
    لذلك نُضيف فحص ملكية الطالب في has_permission نفسها عند وجود student_id.
    هذا يُغلق ثغرة IDOR (CVSS 9.1) — تحقق من ParentStudentLink في طبقة الصلاحيات.
    """

    message = "هذا الطلب لأولياء الأمور والمديرين فقط."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # المدير والسوبر يوزر لا يحتاجان فحص ملكية
        if request.user.is_admin() or request.user.is_superuser:
            return True

        if not request.user.has_role("parent"):
            return False

        # ✅ IDOR Fix (Task 2 — Meeting 2026-04-03):
        # إذا كان الـ endpoint يتضمن student_id في الـ URL kwargs،
        # تحقق من أن ولي الأمر يملك ParentStudentLink مع هذا الطالب.
        # هذا يمنع Parent A من رؤية بيانات أبناء Parent B عبر تغيير الـ student_id.
        student_id = view.kwargs.get("student_id")
        if student_id:
            return ParentStudentLink.objects.filter(
                parent=request.user,
                student_id=student_id,
            ).exists()

        # لا student_id في الـ URL → السماح (مثل قائمة الأبناء المفلترة)
        return True

    def has_object_permission(self, request, view, obj):
        """
        دفاع عميق إضافي للـ CBVs:
        المدير/superuser يمر مباشرة.
        ولي الأمر يجب أن يملك رابط ParentStudentLink نشط مع الطالب.
        الكائن obj يجب أن يكون طالب (CustomUser) أو يملك خاصية student.
        """
        # ── المدير يمر بدون قيد ──
        if request.user.is_superuser or request.user.is_admin():
            return True

        # ── تحديد الطالب من الكائن ──
        student = getattr(obj, "student", obj)

        # ── التحقق من وجود رابط ولي أمر نشط ──
        return ParentStudentLink.objects.filter(
            parent=request.user,
            student=student,
        ).exists()


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
        return request.user.is_same_department(dept)
