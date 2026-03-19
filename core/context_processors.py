def school_context(request):
    if request.user.is_authenticated:
        school = request.user.get_school()
        role   = request.user.get_role()
        return {"current_school": school, "current_role": role}
    return {"current_school": None, "current_role": None}
