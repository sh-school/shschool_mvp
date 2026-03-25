def school_context(request):
    from core.models import School

    if request.user.is_authenticated:
        school = request.user.get_school()
        role = request.user.get_role()
    else:
        school = School.objects.filter(is_active=True).first()
        role = None
    return {"current_school": school, "current_role": role}


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
