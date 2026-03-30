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
# 0. ROLE INHERITANCE — وراثة الأدوار التلقائية (v6)
# ══════════════════════════════════════════════════════════════════════

ROLE_INHERITS = {
    # child → parent (يرث كل صلاحياته الأكاديمية)
    "coordinator": "teacher",           # المنسق يرث المعلم
    "ese_teacher": "teacher",           # معلم ESE يرث المعلم
    "vice_academic": "coordinator",     # النائب الأكاديمي يرث المنسق
    "vice_admin": "admin_supervisor",   # النائب الإداري يرث المشرف الإداري
    "principal": "vice_academic",       # المدير يرث النائب الأكاديمي
    # v7 — مساعدون يرثون من أساتذتهم
    "teacher_assistant": "teacher",     # مساعد المعلم يرث المعلم (جدول + حضور)
    "ese_assistant": "ese_teacher",     # مساعد ESE يرث معلم ESE
    "activities_coordinator": "coordinator",  # منسق أنشطة يرث المنسق
    "transport_officer": "bus_supervisor",    # مسؤول نقل يرث مشرف النقل
}


def expand_roles(roles: set) -> set:
    """
    يوسّع مجموعة أدوار لتشمل كل دور يرث منها.

    مثال:
        expand_roles({"teacher"})
        → {"teacher", "ese_teacher", "coordinator", "vice_academic", "principal"}

    ملاحظة: تُستخدم فقط للصلاحيات ذات الطبيعة الوراثية (الأكاديمية).
    الصلاحيات المتخصصة (nurse, librarian...) تبقى صريحة.
    """
    expanded = set(roles)
    changed = True
    while changed:
        changed = False
        for child, parent in ROLE_INHERITS.items():
            if parent in expanded and child not in expanded:
                expanded.add(child)
                changed = True
    return expanded


# ══════════════════════════════════════════════════════════════════════
# 1. PERMISSION CONSTANTS — ثوابت الصلاحيات لكل نظام فرعي
# ══════════════════════════════════════════════════════════════════════

# ── الجدول الدراسي والحصص ────────────────────────────────────────
SCHEDULE_VIEW = {
    "principal", "vice_academic", "vice_admin", "coordinator",
    "teacher", "ese_teacher", "academic_advisor",
    "student", "parent",
    # v7 — جديد:
    "teacher_assistant", "ese_assistant",       # يحتاجون لرؤية جدول فصولهم
    "activities_coordinator",                   # يحتاج الجدول لتنسيق الأنشطة
    "speech_therapist", "occupational_therapist",  # جلسات الطلاب
    "transport_officer",                        # توقيت الدراسة للنقل
}
SCHEDULE_MANAGE = {"principal", "vice_academic"}
SCHEDULE_SWAP_REQUEST = {"teacher", "ese_teacher", "teacher_assistant"}  # v7: مساعد المعلم يطلب تبديل
SCHEDULE_SWAP_APPROVE = {"coordinator"}  # تخصصه فقط
SCHEDULE_SUBSTITUTE_ASSIGN = {"coordinator", "activities_coordinator"}  # v7: منسق الأنشطة يُسند للأنشطة
SCHEDULE_SUBSTITUTE_APPROVE = {"principal", "vice_academic", "vice_admin"}

# ── الحضور والغياب ──────────────────────────────────────────────
ATTENDANCE_RECORD = {
    "teacher", "ese_teacher", "coordinator", "admin_supervisor",
    "teacher_assistant", "ese_assistant",   # v7: يسجّلون تحت إشراف المعلم
}
ATTENDANCE_VIEW_ALL = {
    "principal", "vice_academic", "vice_admin", "admin_supervisor", "social_worker",
    "transport_officer",   # v7: يحتاج رؤية الحضور لتنظيم النقل
    "activities_coordinator",  # v7: يتابع حضور الأنشطة
}
ATTENDANCE_VIEW_DEPT = {"coordinator"}
ATTENDANCE_VIEW_OWN = {"teacher", "ese_teacher", "teacher_assistant", "ese_assistant"}
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
BEHAVIOR_RECORD = {
    "teacher", "ese_teacher", "coordinator", "social_worker", "admin_supervisor",
    "activities_coordinator",  # v7: يُسجّل سلوك خلال الأنشطة
}
BEHAVIOR_MANAGE = {"principal", "vice_admin", "vice_academic", "social_worker"}
BEHAVIOR_COMMITTEE = {"principal", "vice_admin", "vice_academic", "social_worker", "specialist"}
BEHAVIOR_VIEW_ALL = {
    "principal", "vice_admin", "vice_academic", "social_worker", "psychologist",
    "activities_coordinator",  # v7: يرى سلوك الطلاب في الأنشطة
}
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
# bus_supervisor = مشرف الحافلة (ميداني — يرافق الطلاب)
# transport_officer = مسؤول النقل (إداري — يُدير المنظومة كاملاً)
TRANSPORT_FULL = {"bus_supervisor", "transport_officer"}   # v7: transport_officer يدير النظام
TRANSPORT_MANAGE = {"principal", "vice_admin", "transport_officer"}  # v7: transport_officer يُدير
TRANSPORT_VIEW = {"parent"}

# ── التحليلات والتقارير ─────────────────────────────────────────
ANALYTICS_FULL = {"principal", "vice_academic", "vice_admin"}
ANALYTICS_DEPT = {"coordinator", "activities_coordinator"}  # v7: منسق الأنشطة يرى تحليلات قسمه
ANALYTICS_OWN = {"teacher", "ese_teacher", "teacher_assistant", "ese_assistant"}
ANALYTICS_VIEW = {
    "social_worker", "psychologist", "academic_advisor", "nurse", "librarian",
    "speech_therapist", "occupational_therapist",   # v7: يحتاجون لمتابعة تقدم طلابهم
    "activities_coordinator",                       # v7: يتابع مشاركة الأنشطة
    "transport_officer",                            # v7: إحصائيات النقل
}

# ── إدارة المستخدمين والنظام ────────────────────────────────────
USER_MANAGE = {"principal"}
SYSTEM_ADMIN = {"platform_developer"}

# ── الجودة ──────────────────────────────────────────────────────
QUALITY_MANAGE = {"principal", "vice_admin", "vice_academic"}
QUALITY_VIEW = {
    "coordinator", "teacher", "specialist", "social_worker", "psychologist",
    "activities_coordinator",   # v7: يرى خطة الجودة المتعلقة بالأنشطة
    "speech_therapist", "occupational_therapist",  # v7: يتابعون أهدافهم في الخطة
}
QUALITY_EVALUATE = ALL_STAFF_ROLES  # الجميع يُقيَّم

# ── الإشعارات (إرسال جماعي) ─────────────────────────────────────
NOTIFICATION_BROADCAST = {"principal", "vice_admin", "vice_academic"}

# ── الخطة التشغيلية ─────────────────────────────────────────────
STAGING_MANAGE = {"principal", "vice_academic", "vice_admin"}


# ══════════════════════════════════════════════════════════════════════
# 2. ROLE GROUPS — مجموعات جاهزة للاستخدام في الديكوريتور
# ══════════════════════════════════════════════════════════════════════

# القيادة (T1 + T2)
LEADERSHIP = TIER_1_LEADERSHIP | TIER_2_DEPUTIES
# الطاقم الأكاديمي
ACADEMIC_STAFF = ACADEMIC_ROLES
# كل الطاقم (ليس طالب أو ولي أمر)
ALL_STAFF = ALL_STAFF_ROLES
# أكاديميون + إداريون (لوحة التحكم) — v7: يشمل جميع الأدوار الجديدة
DASHBOARD_ROLES = LEADERSHIP | TIER_3_SUPERVISORS | {
    "teacher", "social_worker", "nurse", "librarian",
    # v7 — الأدوار الجديدة التي تحتاج داشبورد:
    "teacher_assistant", "ese_assistant",
    "speech_therapist", "occupational_therapist",
    "receptionist", "transport_officer",
    "bus_supervisor", "it_technician",
    "psychologist", "academic_advisor",
    "ese_teacher",
}


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

    # توسيع الأدوار لتشمل الأدوار الوارثة (coordinator ← teacher، إلخ)
    expanded_roles = expand_roles(set(roles))

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("login")
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            user_role = request.user.get_role()
            if user_role not in expanded_roles:
                return _forbidden_response(
                    request,
                    f"ليس لديك صلاحية الوصول — دورك: {user_role or 'غير محدد'}",
                )
            return view_func(request, *args, **kwargs)

        wrapper._required_roles = tuple(expanded_roles)
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

    expanded = expand_roles(set(roles))

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

            if user_role not in expanded:
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

        wrapper._required_roles = tuple(expanded)
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

def is_leadership(user):
    """
    يتحقق إذا كان المستخدم من القيادة العليا (T1-T2) — مدير أو نائب.
    لا يشمل دور admin (الإداري العادي T4).
    تُستخدم في الـ views مباشرة: if not is_leadership(request.user)
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.get_role() in ("principal", "vice_admin", "vice_academic")


def can_manage_department(user, department):
    """
    يتحقق إذا كان المستخدم يستطيع إدارة قسم معيّن.
    القيادة تدير الكل. المنسق يدير قسمه فقط.
    يقبل: اسم نصي أو كائن Department.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    role = user.get_role()
    if role in LEADERSHIP:
        return True
    if role == "coordinator":
        return user.is_same_department(department)
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
        # v7 — الأدوار الجديدة التي تحتاج رؤية بيانات الطلاب:
        "teacher_assistant", "ese_assistant",        # يعملون مع طلاب مباشرة
        "speech_therapist", "occupational_therapist",  # جلسات علاج فردية
        "activities_coordinator",                    # يتابع مشاركة الطلاب في الأنشطة
    )


def get_teacher_student_ids(user):
    """
    يُعيد قائمة IDs الطلاب المرئيّين حسب دور المستخدم:

    - superuser / القيادة / الأخصائيون → None (كل الطلاب)
    - المنسق → طلاب كل معلمي قسمه + طلاب فصوله الشخصية + حصص الإشغال
    - المعلم → طلاب فصوله فقط + حصص الإشغال (اليوم)

    يعتمد على ScheduleSlot (الجدول الأسبوعي) — أكثر ثباتاً من Sessions اليومية.

    Usage:
        student_ids = get_teacher_student_ids(request.user)
        if student_ids is None:
            qs = Student.objects.all()  # admin — no filter
        else:
            qs = Student.objects.filter(id__in=student_ids)
    """
    from django.conf import settings

    from core.models import Membership, StudentEnrollment

    if not user or not user.is_authenticated:
        return set()
    if user.is_superuser:
        return None  # all students

    role = user.get_role()

    # القيادة والأخصائيون يرون كل الطلاب
    ALL_STUDENTS_ROLES = {
        "principal", "vice_admin", "vice_academic",
        "social_worker", "psychologist", "academic_advisor",
        "admin_supervisor", "nurse",
        # v7 — الأدوار الجديدة التي تحتاج رؤية كل الطلاب:
        "speech_therapist", "occupational_therapist",  # يُحال إليهم طلاب من مختلف الفصول
        "transport_officer",   # يحتاج كل طلاب النقل لإسناد الحافلات
        "activities_coordinator",  # يُنسّق أنشطة لكل الطلاب
    }
    if role in ALL_STUDENTS_ROLES:
        return None

    year = getattr(settings, "CURRENT_ACADEMIC_YEAR", "2025-2026")
    school = user.get_school()

    from operations.models import ScheduleSlot, SubstituteAssignment

    # ── 1) فصول المعلم الشخصية من الجدول الأسبوعي ──
    own_class_ids = set(
        ScheduleSlot.objects.filter(
            teacher=user, is_active=True, academic_year=year,
        ).values_list("class_group_id", flat=True)
    )

    # ── 2) المنسق: فصول كل معلمي قسمه ──
    dept_class_ids = set()
    if role == "coordinator" and school:
        dept_obj = user.department_obj
        if dept_obj:
            dept_teacher_ids = dept_obj.get_teacher_ids()
        else:
            dept_teacher_ids = set()

        if dept_teacher_ids:
            dept_class_ids = set(
                ScheduleSlot.objects.filter(
                    teacher_id__in=dept_teacher_ids,
                    is_active=True,
                    academic_year=year,
                ).values_list("class_group_id", flat=True)
            )

    # ── 3) حصص الإشغال (بديل) — اليوم فقط ──
    import datetime

    today = datetime.date.today()
    substitute_class_ids = set(
        SubstituteAssignment.objects.filter(
            substitute=user,
            status__in=("assigned", "confirmed"),
            absence__date=today,
        ).select_related("slot").values_list("slot__class_group_id", flat=True)
    )

    all_class_ids = own_class_ids | dept_class_ids | substitute_class_ids

    if not all_class_ids:
        return set()

    return set(
        StudentEnrollment.objects.filter(
            class_group_id__in=all_class_ids, is_active=True,
        ).values_list("student_id", flat=True)
    )


def teacher_can_access_student(user, student_id):
    """
    يتحقق إذا كان المعلم/المنسق يمكنه الوصول لطالب معيّن.
    True = يُسمح، False = ممنوع.
    """
    ids = get_teacher_student_ids(user)
    if ids is None:
        return True  # admin/leadership — all access
    return student_id in ids


def get_department_teacher_ids(user):
    """
    يُعيد قائمة IDs المعلمين في قسم المنسق.
    - المنسق → معلمي قسمه/تخصصه في نفس المدرسة
    - القيادة → None (كل المعلمين)
    - المعلم العادي → مجموعة فارغة (لا يرى معلمين آخرين)
    """
    if not user or not user.is_authenticated:
        return set()
    if user.is_superuser:
        return None

    role = user.get_role()
    ALL_TEACHERS_ROLES = {
        "principal", "vice_admin", "vice_academic", "admin_supervisor",
    }
    if role in ALL_TEACHERS_ROLES:
        return None

    if role != "coordinator":
        return set()

    school = user.get_school()
    if not school:
        return set()

    # ✅ v6: استخدام Department FK أولاً
    dept_obj = user.department_obj
    if dept_obj:
        return dept_obj.get_teacher_ids()
    return set()


def get_accessible_modules(user):
    """
    يُعيد قائمة الأنظمة الفرعية التي يمكن للمستخدم الوصول إليها.
    يستخدم Module Registry (v6) مع fallback للقاموس القديم.
    مفيد لعرض القائمة الجانبية (sidebar) ديناميكياً.
    """
    if not user or not user.is_authenticated:
        return []

    # ── محاولة استخدام Module Registry أولاً ──
    from core.module_registry import get_accessible_modules_from_registry, is_registered

    if is_registered("assessments"):
        # Registry مفعّل — نستخدمه
        registry_modules = get_accessible_modules_from_registry(user)
        # أضف dashboard دائماً + استخرج الأسماء فقط للتوافقية
        names = ["dashboard"] + [m["name"] for m in registry_modules]
        # أضف users و system للمشرفين
        if user.is_superuser:
            names.extend(["users", "system"])
        elif user.get_role() in USER_MANAGE:
            names.append("users")
        return names

    # ── Fallback: القاموس القديم (حتى اكتمال الهجرة) ──
    if user.is_superuser:
        return [
            "dashboard", "schedule", "attendance", "assessments",
            "behavior", "clinic", "library", "transport",
            "analytics", "reports", "quality", "notifications",
            "users", "staging", "system",
        ]

    role = user.get_role()
    modules = ["dashboard"]

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
