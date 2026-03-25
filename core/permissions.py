"""
core/permissions.py
══════════════════════════════════════════════════════════════════════
نظام الصلاحيات الاحترافي — SchoolOS RBAC
المرجع: قرار مجلس الوزراء 32/2019 (الهيكل التنظيمي للمدارس)
══════════════════════════════════════════════════════════════════════

المبادئ:
  1. Least Privilege — كل دور يحصل فقط على ما يحتاجه
  2. Defense in Depth — middleware + decorator + view-level checks
  3. Fail Closed — إذا لم يُسمح صراحةً، يُرفض
  4. Department Scoping — المنسق يرى تخصصه فقط
  5. Self-Scoping — المعلم يرى فصوله فقط، الطالب يرى بياناته فقط
"""

from functools import wraps

from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect

from .models.access import (
    ACADEMIC_ROLES,
    ADMIN_ROLES,
    ALL_STAFF_ROLES,
    TIER_1_LEADERSHIP,
    TIER_2_DEPUTIES,
    TIER_3_SUPERVISORS,
)


# ══════════════════════════════════════════════════════════════════════
# 1. PERMISSION CONSTANTS — ثوابت الصلاحيات لكل نظام فرعي
# ══════════════════════════════════════════════════════════════════════

# ── الجدول الدراسي والحصص ────────────────────────────────────────
SCHEDULE_VIEW = {
    "principal", "vice_academic", "vice_admin", "coordinator",
    "teacher", "ese_teacher", "academic_advisor",
    "student", "parent",
}
SCHEDULE_MANAGE = {"principal", "vice_academic"}
SCHEDULE_SWAP_REQUEST = {"teacher", "ese_teacher"}
SCHEDULE_SWAP_APPROVE = {"coordinator"}  # تخصصه فقط
SCHEDULE_SUBSTITUTE_ASSIGN = {"coordinator"}  # تخصصه فقط
SCHEDULE_SUBSTITUTE_APPROVE = {"principal", "vice_academic", "vice_admin"}

# ── الحضور والغياب ──────────────────────────────────────────────
ATTENDANCE_RECORD = {"teacher", "ese_teacher", "admin_supervisor"}
ATTENDANCE_VIEW_ALL = {"principal", "vice_academic", "vice_admin", "admin_supervisor", "social_worker"}
ATTENDANCE_VIEW_DEPT = {"coordinator"}
ATTENDANCE_VIEW_OWN = {"teacher", "ese_teacher"}
ATTENDANCE_VIEW_CHILD = {"parent"}
ATTENDANCE_REPORTS = {"principal", "vice_academic", "vice_admin"}

# ── التقييمات والدرجات ──────────────────────────────────────────
ASSESSMENT_CREATE = {"teacher", "ese_teacher", "coordinator", "vice_academic"}
ASSESSMENT_EDIT = {"teacher", "ese_teacher", "coordinator", "vice_academic"}
ASSESSMENT_VIEW_ALL = {"principal", "vice_academic", "vice_admin"}
ASSESSMENT_VIEW_DEPT = {"coordinator"}
ASSESSMENT_VIEW_OWN = {"teacher", "ese_teacher"}
ASSESSMENT_VIEW_CHILD = {"parent"}
ASSESSMENT_VIEW_SELF = {"student"}

# ── السلوك والانضباط ────────────────────────────────────────────
BEHAVIOR_RECORD = {"teacher", "ese_teacher", "social_worker", "admin_supervisor"}
BEHAVIOR_MANAGE = {"principal", "vice_admin", "vice_academic", "social_worker"}
BEHAVIOR_VIEW_ALL = {"principal", "vice_admin", "vice_academic", "social_worker", "psychologist"}
BEHAVIOR_VIEW_CHILD = {"parent"}
BEHAVIOR_VIEW_SELF = {"student"}

# ── العيادة الصحية ──────────────────────────────────────────────
CLINIC_FULL = {"nurse"}
CLINIC_VIEW = {"principal", "vice_admin"}
CLINIC_VIEW_CHILD = {"parent"}

# ── المكتبة ─────────────────────────────────────────────────────
LIBRARY_FULL = {"librarian"}
LIBRARY_VIEW = {"principal", "vice_admin", "teacher", "coordinator", "student"}

# ── النقل المدرسي ───────────────────────────────────────────────
TRANSPORT_FULL = {"bus_supervisor"}
TRANSPORT_MANAGE = {"principal", "vice_admin"}
TRANSPORT_VIEW = {"parent"}

# ── التحليلات والتقارير ─────────────────────────────────────────
ANALYTICS_FULL = {"principal", "vice_academic", "vice_admin"}
ANALYTICS_DEPT = {"coordinator"}
ANALYTICS_OWN = {"teacher", "ese_teacher"}
ANALYTICS_VIEW = {"social_worker", "psychologist", "academic_advisor", "nurse", "librarian"}

# ── إدارة المستخدمين والنظام ────────────────────────────────────
USER_MANAGE = {"principal"}
SYSTEM_ADMIN = {"platform_developer"}

# ── الجودة ──────────────────────────────────────────────────────
QUALITY_MANAGE = {"principal", "vice_admin", "vice_academic"}
QUALITY_VIEW = {"coordinator", "teacher", "specialist", "social_worker", "psychologist"}
QUALITY_EVALUATE = ALL_STAFF_ROLES  # الجميع يُقيَّم

# ── الإشعارات (إرسال جماعي) ─────────────────────────────────────
NOTIFICATION_BROADCAST = {"principal", "vice_admin", "vice_academic"}

# ── الخطة التشغيلية ─────────────────────────────────────────────
STAGING_MANAGE = {"principal", "vice_academic", "vice_admin", "admin"}


# ══════════════════════════════════════════════════════════════════════
# 2. ROLE GROUPS — مجموعات جاهزة للاستخدام في الديكوريتور
# ══════════════════════════════════════════════════════════════════════

# القيادة (T1 + T2)
LEADERSHIP = TIER_1_LEADERSHIP | TIER_2_DEPUTIES
# الطاقم الأكاديمي
ACADEMIC_STAFF = ACADEMIC_ROLES
# كل الطاقم (ليس طالب أو ولي أمر)
ALL_STAFF = ALL_STAFF_ROLES
# أكاديميون + إداريون (لوحة التحكم)
DASHBOARD_ROLES = LEADERSHIP | TIER_3_SUPERVISORS | {"teacher", "social_worker", "nurse", "librarian"}


# ══════════════════════════════════════════════════════════════════════
# 3. DECORATORS — الديكوريتورات
# ══════════════════════════════════════════════════════════════════════

def _get_user_role(request):
    """يستخلص الدور بأمان — يدعم WSGIRequest و HttpRequest."""
    if not hasattr(request, "user") or not request.user.is_authenticated:
        return None
    return request.user.get_role()


def _forbidden_response(request, message):
    """يُعيد رد مناسب حسب نوع الطلب (API vs HTML)."""
    if request.path.startswith("/api/"):
        return JsonResponse({"error": message, "code": "forbidden"}, status=403)
    return HttpResponseForbidden(
        f"<h2 dir='rtl' style='font-family:Tajawal,sans-serif;padding:40px;color:#B91C1C'>{message}</h2>"
    )


def role_required(*roles):
    """
    ديكوريتور أساسي — يتحقق من أن المستخدم لديه أحد الأدوار المعطاة.
    superuser يمر دائماً.

    Usage:
        @role_required("principal", "vice_academic")
        def my_view(request): ...
    """
    # دعم تمرير مجموعة set أو tuple أو list كعنصر واحد
    if len(roles) == 1 and isinstance(roles[0], (set, frozenset, list, tuple)):
        roles = tuple(roles[0])

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("login")
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            user_role = request.user.get_role()
            if user_role not in roles:
                return _forbidden_response(
                    request,
                    f"ليس لديك صلاحية الوصول — دورك: {user_role or 'غير محدد'}",
                )
            return view_func(request, *args, **kwargs)

        wrapper._required_roles = roles
        return wrapper

    return decorator


def department_scoped(*roles):
    """
    ديكوريتور للصلاحيات المقيّدة بالقسم/التخصص.
    يُمرّر `user_department` كـ kwarg إلى الـ view.
    القيادة (T1+T2) تمر بدون تقييد.

    Usage:
        @department_scoped("coordinator")
        def schedule_dept_view(request, user_department=None): ...
    """
    if len(roles) == 1 and isinstance(roles[0], (set, frozenset, list, tuple)):
        roles = tuple(roles[0])

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("login")
            if request.user.is_superuser:
                return view_func(request, *args, user_department=None, **kwargs)

            user_role = request.user.get_role()
            # القيادة تمر بدون تقييد بالقسم
            if user_role in LEADERSHIP:
                return view_func(request, *args, user_department=None, **kwargs)

            if user_role not in roles:
                return _forbidden_response(
                    request,
                    f"ليس لديك صلاحية الوصول — دورك: {user_role or 'غير محدد'}",
                )

            dept = request.user.department
            if not dept:
                return _forbidden_response(
                    request,
                    "لم يتم تحديد القسم/التخصص في عضويتك — تواصل مع الإدارة",
                )
            kwargs["user_department"] = dept
            return view_func(request, *args, **kwargs)

        wrapper._required_roles = roles
        wrapper._department_scoped = True
        return wrapper

    return decorator


def permission_required(permission_set):
    """
    ديكوريتور يقبل مجموعة صلاحيات (set) — أنظف من تمرير أسماء الأدوار يدوياً.

    Usage:
        @permission_required(ASSESSMENT_CREATE)
        def create_assessment(request): ...
    """
    return role_required(permission_set)


# ══════════════════════════════════════════════════════════════════════
# 4. SHORTCUT DECORATORS — ديكوريتورات مختصرة
# ══════════════════════════════════════════════════════════════════════

def staff_required(view_func):
    """أي موظف بالمدرسة (ليس طالب أو ولي أمر)."""
    return role_required(ALL_STAFF | {"specialist"})(view_func)


def leadership_required(view_func):
    """المدير ونوابه فقط (T1 + T2)."""
    return role_required(LEADERSHIP)(view_func)


def academic_required(view_func):
    """الطاقم الأكاديمي: مدير + نائب أكاديمي + منسق + معلم."""
    return role_required(ACADEMIC_STAFF)(view_func)


def nurse_required(view_func):
    """الممرض + القيادة."""
    return role_required("nurse", "principal", "vice_admin")(view_func)


def librarian_required(view_func):
    """أمين المكتبة + القيادة."""
    return role_required("librarian", "principal", "vice_admin")(view_func)


def bus_supervisor_required(view_func):
    """مشرف النقل + القيادة."""
    return role_required("bus_supervisor", "principal", "vice_admin")(view_func)


def coordinator_required(view_func):
    """المنسق + القيادة."""
    return role_required("coordinator", "principal", "vice_academic", "vice_admin")(view_func)


def social_worker_required(view_func):
    """الأخصائي الاجتماعي + القيادة."""
    return role_required("social_worker", "specialist", "principal", "vice_admin")(view_func)


def psychologist_required(view_func):
    """الأخصائي النفسي + القيادة — بيانات سرية."""
    return role_required("psychologist", "principal", "vice_admin")(view_func)


def schedule_manage_required(view_func):
    """إدارة الجدول الدراسي — المدير + النائب الأكاديمي."""
    return role_required(SCHEDULE_MANAGE)(view_func)


def schedule_view_required(view_func):
    """عرض الجدول — معظم الأدوار."""
    return role_required(SCHEDULE_VIEW)(view_func)


# ══════════════════════════════════════════════════════════════════════
# 5. UTILITY FUNCTIONS — دوال مساعدة
# ══════════════════════════════════════════════════════════════════════

def is_admin_or_principal(user):
    """
    يتحقق إذا كان المستخدم مديراً أو نائباً — دالة مساعدة (ليست ديكوريتور).
    تُستخدم في الـ views مباشرة: if not is_admin_or_principal(request.user)
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.get_role() in ("principal", "vice_admin", "vice_academic", "admin")


def can_manage_department(user, department):
    """
    يتحقق إذا كان المستخدم يستطيع إدارة قسم معيّن.
    القيادة تدير الكل. المنسق يدير قسمه فقط.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    role = user.get_role()
    if role in LEADERSHIP:
        return True
    if role == "coordinator":
        return user.department == department
    return False


def can_view_student_data(user, student=None):
    """
    يتحقق إذا كان المستخدم يستطيع رؤية بيانات طالب معيّن.
    - القيادة والأخصائيون يرون الكل
    - المعلم يرى طلاب فصوله (يجب التحقق في الـ view)
    - ولي الأمر يرى ابنه فقط (يجب التحقق في الـ view)
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    role = user.get_role()
    return role in (
        "principal", "vice_admin", "vice_academic",
        "coordinator", "teacher", "ese_teacher",
        "social_worker", "psychologist", "academic_advisor",
        "admin_supervisor", "nurse",
    )


def get_accessible_modules(user):
    """
    يُعيد قائمة الأنظمة الفرعية التي يمكن للمستخدم الوصول إليها.
    مفيد لعرض القائمة الجانبية (sidebar) ديناميكياً.
    """
    if not user or not user.is_authenticated:
        return []
    if user.is_superuser:
        return [
            "dashboard", "schedule", "attendance", "assessments",
            "behavior", "clinic", "library", "transport",
            "analytics", "reports", "quality", "notifications",
            "users", "staging", "system",
        ]

    role = user.get_role()
    modules = ["dashboard"]  # الكل يرى لوحة التحكم

    # بناء القائمة حسب الدور
    module_access = {
        "schedule": SCHEDULE_VIEW,
        "attendance": ATTENDANCE_VIEW_ALL | ATTENDANCE_RECORD | ATTENDANCE_VIEW_DEPT | ATTENDANCE_VIEW_OWN | {"parent", "student"},
        "assessments": ASSESSMENT_CREATE | ASSESSMENT_VIEW_ALL | {"parent", "student"},
        "behavior": BEHAVIOR_MANAGE | BEHAVIOR_RECORD | {"parent", "student"},
        "clinic": CLINIC_FULL | CLINIC_VIEW | {"parent"},
        "library": LIBRARY_FULL | LIBRARY_VIEW,
        "transport": TRANSPORT_FULL | TRANSPORT_MANAGE | TRANSPORT_VIEW,
        "analytics": ANALYTICS_FULL | ANALYTICS_DEPT | ANALYTICS_OWN | ANALYTICS_VIEW,
        "reports": {"principal", "vice_academic", "vice_admin", "coordinator", "teacher"},
        "quality": QUALITY_MANAGE | QUALITY_VIEW,
        "notifications": ALL_STAFF_ROLES | {"specialist"},
        "users": USER_MANAGE,
        "staging": STAGING_MANAGE,
    }

    for module, allowed in module_access.items():
        if role in allowed:
            modules.append(module)

    return modules


# ══════════════════════════════════════════════════════════════════════
# 6. INTERNAL ONLY — حماية endpoints حساسة
# ══════════════════════════════════════════════════════════════════════

def internal_only(view_func):
    """يسمح فقط بالوصول من عناوين IP الداخلية — لحماية /metrics و endpoints حساسة."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        from django.conf import settings as _s

        xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip = xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")
        allowed = list(getattr(_s, "METRICS_ALLOWED_IPS", [])) + ["127.0.0.1", "::1"]
        if ip not in allowed:
            return HttpResponseForbidden("Access denied — internal only.")
        return view_func(request, *args, **kwargs)

    return wrapper
