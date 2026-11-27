"""
student_affairs/chronic_views.py — البيانُ الصحّيُّ في صفحة الطالب (W-20261020-033، W-20261127-006)
═══════════════════════════════════════════════════════════════════════════════════════
كشفُ اسم الحالة المزمنة بنقرةٍ مقصودةٍ (POST) تُسجَّل. المنطقُ في `clinic.health_access`. والمسارُ هنا
لا تحت `/clinic/` لأنّ بوّابةَ الوسيط تحجب بادئةَ العيادة عن المعلّم.
وتبويبُ «العيادة» يُجلب من هنا عند النقر ويُدقَّق (CLN-03).
"""

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from clinic.health_access import reveal_chronic, student_clinic_tab
from clinic.selectors import school_student
from core.capabilities import capability_required
from wings.scope import student_scope_for


@login_required
@capability_required("clinic.chronic_name")
@require_POST
def reveal_chronic_name(request, student_id):
    name = reveal_chronic(request, student_id)
    return render(request, "clinic/partials/_chronic_name.html", {"name": name})


@login_required
@capability_required("student_affairs.follow_up")
@require_GET
@never_cache
def student_clinic_tab_partial(request: HttpRequest, student_id: str) -> HttpResponse:
    """محتوى تبويب «العيادة» — بحارس صفحة الطالب نفسِه: القدرةُ ثمّ النطاقُ ثمّ المدرسة."""
    school = request.school  # type: ignore[attr-defined]
    scope = student_scope_for(request)
    scope.require_student(student_id)
    student = school_student(school, student_id)
    context = student_clinic_tab(request, school, student, summary_only=scope.clinic_summary_only)
    return render(
        request,
        "student_affairs/partials/student_clinic_tab.html",
        {**context, "student": student, "limited": scope.is_wing_bound},
    )
