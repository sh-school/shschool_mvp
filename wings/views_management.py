"""شاشةُ «إدارة الأجنحة»: مشرفُ كلّ جناحٍ وميدانيُّه والإنابةُ الحاليّة وسجلُّ التعيينات.

يعيّن المديرُ والنائبُ الإداريّ ومنسّقُ شؤون الطلبة. والقراءةُ في `assignment_selectors`
والكتابةُ في `assignment_services`.
"""

from __future__ import annotations

import datetime as dt

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.academic_calendar import academic_year_for_school
from core.capabilities import capability_required
from core.models import Wing, WingAssignment
from core.user_selectors import school_user_or_none

from .assignment_selectors import eligible_people, management_rows
from .assignment_services import assign_wing_role


@login_required
@capability_required("wings.manage")
def management(request):
    """لكلّ جناحٍ: المشرفُ والميدانيّ والإنابةُ الحاليّة، وسجلُّ تعييناته، ونموذجُ التعيين."""
    school = request.school
    year = academic_year_for_school(school)
    today = timezone.localdate()
    return render(
        request,
        "wings/management.html",
        {
            "rows": management_rows(school, year, today),
            "people": eligible_people(school),
            "roles": WingAssignment.ROLES,
            "today": today,
            "subtitle": f"من يشرف على كلّ جناحٍ اليوم ومن يعمل فيه ميدانيّاً · {year}",
        },
    )


@login_required
@capability_required("wings.manage")
@require_POST
def management_assign(request, code):
    """يعيّن مشرفاً أو ميدانيّاً لجناحٍ من تاريخ — فيُغلق تعيينُ سابقِه ولا يُحذف."""
    school = request.school
    wing = get_object_or_404(
        Wing, school=school, code=code, academic_year=academic_year_for_school(school)
    )
    user = school_user_or_none(school, request.POST.get("user"))
    if user is None:
        messages.error(request, "اختر المعيَّن.")
        return redirect("wings:management")
    try:
        start = dt.date.fromisoformat(request.POST.get("start_date") or "")
    except ValueError:
        start = timezone.localdate()
    try:
        assignment = assign_wing_role(
            wing=wing,
            role=request.POST.get("role", ""),
            user=user,
            by=request.user,
            start_date=start,
        )
    except ValidationError as err:
        for texts in err.message_dict.values():
            for text in texts:
                messages.error(request, text)
        return redirect("wings:management")
    messages.success(
        request,
        f"عُيّن {user.full_name} {assignment.get_role_display()} لـ{wing.name} من {start}.",
    )
    return redirect("wings:management")
