def school_context(request):
    from core.models import School
    if request.user.is_authenticated:
        school = request.user.get_school()
        role = request.user.get_role()
    else:
        school = School.objects.filter(is_active=True).first()
        role = None
    return {"current_school": school, "current_role": role}
