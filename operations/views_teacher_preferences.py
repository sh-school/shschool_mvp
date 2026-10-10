"""views_teacher_preferences.py — اطّلاعٌ على تفضيلات المعلّمين في الجدول (W-20261010-026، D-330م).

قراءةٌ فقط: المديرُ والنائبُ الأكاديميّ يريان معلّمي المدرسة كلَّهم، ومنسّقُ المادّة معلّمي قسمه.
والتعديلُ يبقى لصاحب التفضيل (`teacher_preferences`، قدرة `schedule.preferences` التي لم تُوسَّع).
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.views.decorators.http import require_GET

from core.academic_calendar import academic_year_for
from core.capabilities import capability_required
from core.models import AuditLog

from .selectors import preference_rows, teachers_in_scope


@login_required
@capability_required("schedule.preferences_view")
@require_GET
def teacher_preferences_overview(request):
    """قائمةُ تفضيلات المعلّمين بنطاق المستخدم، بلا حقل تحرير."""
    school = request.school
    year = request.GET.get("year") or academic_year_for(request)

    teachers = teachers_in_scope(request.user, school)
    if teachers is None:
        # منسّقٌ بلا قسمٍ: لا نطاقَ له فلا يرى أحداً، ويُسجَّل المنعُ.
        AuditLog.log(
            user=request.user,
            action="view",
            model_name="TeacherPreference",
            object_repr="رُفض اطّلاعُ تفضيلات المعلّمين: no_department",
            school=school,
            request=request,
        )
        raise PermissionDenied

    # سقفُ السابعات قرارٌ إداريّ في حقّ المعلّم: يراه المديرُ وحدَه (المواصفة).
    show_last = request.user.get_role() == "principal"
    rows, with_pref = preference_rows(teachers, school, year)

    return render(
        request,
        "schedule/teacher_preferences_overview.html",
        {
            "year": year,
            "rows": rows,
            "total": len(rows),
            "with_pref": with_pref,
            "show_last": show_last,
        },
    )
