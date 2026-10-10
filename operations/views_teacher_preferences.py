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
from core.models import AuditLog, CustomUser, Membership
from core.permissions import get_department_teacher_ids

from .models import ScheduleSlot, TeacherPreference

#: من يُعدّ معلّماً في قائمة المدرسة — نفسُ تقرير أعباء المعلمين.
TEACHING_ROLE_NAMES = ("teacher", "coordinator", "ese_teacher", "e_projects_coordinator")
DAY_NAMES = dict(ScheduleSlot.DAYS)


def _teachers_in_scope(request, school):
    """معلّمو نطاق المستخدم، أو `None` إن كان منسّقاً بلا قسمٍ فيُرفض."""
    dept_ids = get_department_teacher_ids(request.user)
    if dept_ids is None:
        ids = Membership.objects.filter(
            school=school, is_active=True, role__name__in=TEACHING_ROLE_NAMES
        ).values_list("user_id", flat=True)
        return CustomUser.objects.filter(id__in=ids).order_by("full_name")
    if not dept_ids:
        return None
    return CustomUser.objects.filter(id__in=dept_ids).order_by("full_name")


@login_required
@capability_required("schedule.preferences_view")
@require_GET
def teacher_preferences_overview(request):
    """قائمةُ تفضيلات المعلّمين بنطاق المستخدم، بلا حقل تحرير."""
    school = request.school
    year = request.GET.get("year") or academic_year_for(request)

    teachers = _teachers_in_scope(request, school)
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

    prefs = {
        p.teacher_id: p
        for p in TeacherPreference.objects.filter(
            school=school, academic_year=year, teacher__in=teachers
        )
    }
    # سقفُ السابعات قرارٌ إداريّ في حقّ المعلّم: يراه المديرُ وحدَه (المواصفة).
    show_last = request.user.get_role() == "principal"
    rows = []
    for teacher in teachers:
        pref = prefs.get(teacher.id)
        rows.append(
            {
                "teacher": teacher,
                "pref": pref,
                "free_day": DAY_NAMES.get(pref.free_day, "") if pref else "",
            }
        )

    return render(
        request,
        "schedule/teacher_preferences_overview.html",
        {
            "year": year,
            "rows": rows,
            "total": len(rows),
            "with_pref": len(prefs),
            "show_last": show_last,
        },
    )
