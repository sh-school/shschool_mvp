def school_context(request):
    from django.conf import settings

    from core.models import School

    if request.user.is_authenticated:
        school = request.user.get_school()
        role = request.user.get_role()
        dept_obj = request.user.department_obj
        department = dept_obj.name if dept_obj else ""
    else:
        school = School.objects.filter(is_active=True).first()
        role = None
        dept_obj = None
        department = ""
    # الزمن الأكاديمي يُشتقّ من تقويم الوزارة لا من ثابتٍ في الإعدادات:
    # `CURRENT_ACADEMIC_YEAR` تجاوزه الزمن فعلاً — ظلّ يقول «2025-2026» بعد
    # بدء عام 2026-2027 — ولا شيء يكشف ذلك لأن القيمة صحيحةٌ نحوياً.
    now = None
    if school is not None:
        from core.academic_calendar import AcademicCalendar

        now = AcademicCalendar.current(school)

    return {
        "current_school": school,
        "current_role": role,
        "current_department": department,
        "current_department_obj": dept_obj,
        "current_year": now.year if now else None,
        "current_year_name": now.year_name if now else "",
        "current_semester": now.semester if now else None,
        "platform_version": getattr(settings, "PLATFORM_VERSION", "5.1"),
    }


def permissions_context(request):
    """يُضيف صلاحيات المستخدم ووحداته المتاحة لكل قالب — لعرض القائمة الجانبية ديناميكياً."""
    if not request.user.is_authenticated:
        return {
            "accessible_modules": [],
            "registry_modules": [],
            "is_leadership": False,
            "is_staff_member": False,
            "is_developer": False,
        }

    from core.module_registry import get_accessible_modules_from_registry
    from core.permissions import get_accessible_modules

    return {
        "accessible_modules": get_accessible_modules(request.user),
        "registry_modules": get_accessible_modules_from_registry(request.user),
        "is_leadership": request.user.is_leadership(),
        "is_admin_role": request.user.is_leadership(),
        "is_staff_member": request.user.is_staff_member(),
        "is_developer": (
            request.user.is_superuser
            or request.user.groups.filter(name__iexact="developers").exists()
        ),
    }


def quality_nav_context(request):
    """إضافة متغيرات لجنة الجودة للقائمة — لعرض روابط المراجعة لأعضاء اللجنة"""
    if not request.user.is_authenticated:
        return {}

    from quality.models import QualityCommitteeMember

    school = request.user.get_school()
    if not school:
        return {}

    # الاستعلام لا يُرشّح بالعام — وكان هنا إسنادٌ ميّت له، فحُذف.
    # MTG-2026-005: merged 2 queries into 1
    member_types = set(
        QualityCommitteeMember.objects.filter(
            school=school,
            user=request.user,
            is_active=True,
        ).values_list("committee_type", flat=True)
    )

    return {
        "is_quality_reviewer": QualityCommitteeMember.REVIEW in member_types,
        "is_quality_executor": QualityCommitteeMember.EXECUTOR in member_types,
    }
