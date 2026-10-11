"""مُنتقيات operations للقراءة فقط — اطّلاع تفضيلات المعلّمين (W-20261010-026)."""

from __future__ import annotations

from core.models import CustomUser, Membership
from core.permissions import TEACHING_STAFF_ROLES, get_department_teacher_ids

from .models import ScheduleSlot, TeacherPreference

DAY_NAMES = dict(ScheduleSlot.DAYS)


def teachers_in_scope(user, school):
    """معلّمو نطاق المستخدم، أو `None` إن كان منسّقاً بلا قسمٍ (لا نطاقَ له)."""
    dept_ids = get_department_teacher_ids(user)
    if dept_ids is None:
        ids = Membership.objects.filter(
            school=school, is_active=True, role__name__in=TEACHING_STAFF_ROLES
        ).values_list("user_id", flat=True)
        return CustomUser.objects.filter(id__in=ids).order_by("full_name")
    if not dept_ids:
        return None
    return CustomUser.objects.filter(id__in=dept_ids).order_by("full_name")


def preference_rows(teachers, school, year) -> tuple[list[dict], int]:
    """صفوفُ الجدول (معلّم، تفضيله، يومُ فراغه) وعددُ من سجّل تفضيله."""
    prefs = {
        p.teacher_id: p
        for p in TeacherPreference.objects.filter(
            school=school, academic_year=year, teacher__in=teachers
        )
    }
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
    return rows, len(prefs)
