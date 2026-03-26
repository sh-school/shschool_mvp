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
    return {
        "current_school": school,
        "current_role": role,
        "current_department": department,
        "current_department_obj": dept_obj,
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
        }

    from core.module_registry import get_accessible_modules_from_registry
    from core.permissions import get_accessible_modules

    return {
        "accessible_modules": get_accessible_modules(request.user),
        "registry_modules": get_accessible_modules_from_registry(request.user),
        "is_leadership": request.user.is_leadership(),
        "is_admin_role": request.user.is_admin_or_principal(),
        "is_staff_member": request.user.is_staff_member(),
    }


def quality_nav_context(request):
    """إضافة متغيرات لجنة الجودة للقائمة — لعرض روابط المراجعة لأعضاء اللجنة"""
    if not request.user.is_authenticated:
        return {}

    from django.conf import settings

    from quality.models import QualityCommitteeMember

    school = request.user.get_school()
    if not school:
        return {}

    year = getattr(settings, "CURRENT_ACADEMIC_YEAR", "2025-2026")
    is_reviewer = QualityCommitteeMember.objects.filter(
        school=school,
        user=request.user,
        committee_type=QualityCommitteeMember.REVIEW,
        is_active=True,
    ).exists()
    is_executor_member = QualityCommitteeMember.objects.filter(
        school=school,
        user=request.user,
        committee_type=QualityCommitteeMember.EXECUTOR,
        is_active=True,
    ).exists()

    return {
        "is_quality_reviewer": is_reviewer,
        "is_quality_executor": is_executor_member,
    }
