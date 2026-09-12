"""شاشةُ أجنحة المدرسة — طابقان، خمسةُ أجنحة، وجرسٌ يُقرأ بالساعة."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from core.academic_calendar import academic_year_for_school
from core.permissions import role_required
from operations.bells import day_type_for

from .services import bell_tables, floors_overview

DAY_LABEL = {"regular": "الأحد – الأربعاء", "thursday": "الخميس"}


@login_required
@role_required(
    "principal",
    "vice_admin",
    "vice_academic",
    "admin_supervisor",
    "platform_developer",
)
def floors(request):
    school = request.user.get_school()
    now = timezone.localtime()
    year = academic_year_for_school(school)
    day_type = day_type_for(now.date())

    panels = floors_overview(school, year, now)
    return render(
        request,
        "wings/floors.html",
        {
            "panels": panels,
            "tables": bell_tables(school),
            "now": now,
            "year": year,
            "day_label": DAY_LABEL.get(day_type, "عطلة — لا دوام"),
            "is_school_day": bool(day_type),
            "wing_count": sum(len(panel.wings) for panel in panels),
            "section_count": sum(panel.section_count for panel in panels),
            "student_count": sum(panel.student_count for panel in panels),
        },
    )
