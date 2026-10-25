"""مُنتقيات operations للقراءة فقط — اطّلاع تفضيلات المعلّمين (W-20261010-026)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from core.models import CustomUser, Membership
from core.permissions import TEACHING_STAFF_ROLES, get_department_teacher_ids

from .models import ScheduleSlot, TeacherPreference

DAY_NAMES = dict(ScheduleSlot.DAYS)


def teachers_in_scope(user: Any, school: Any) -> Any:
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


def preference_rows(teachers: Any, school: Any, year: Any) -> tuple[list[dict], int]:
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
                "free_day": DAY_NAMES.get(pref.free_day, "")
                if pref and pref.free_day is not None
                else "",
            }
        )
    return rows, len(prefs)


def scheduled_slots(
    student: Any, school: Any, start: dt.date, end: dt.date
) -> set[tuple[dt.date, dt.time]]:
    """خاناتُ جدول الطالب في المدّة `{(تاريخ، بداية)}` من الشعبة التي كان فيها **ذلك اليوم** (D-201م).

    بعد الانتقال تُقرأ أيّامُ ما قبله من شعبته القديمة لا الحاليّة، وإلا حُكم عليها بجدول شعبةٍ لم يكن فيها.
    والمدّةُ `[enrolled_at، left_at]` بدلالة `on_roll` نفسِها؛ وقيدٌ معطَّلٌ بلا `left_at` لا يُخمَّن.
    """
    from core.models import StudentEnrollment

    from .models import Session

    spans: dict = {}
    for class_id, enrolled_at, left_at, is_active in (
        StudentEnrollment.objects.filter(student=student)
        .order_by("enrolled_at", "id")
        .values_list("class_group_id", "enrolled_at", "left_at", "is_active")
    ):
        if left_at is None and not is_active:
            continue
        # أوّلُ قيدٍ تاريخُه تاريخُ الاستيراد لا بدءُ الدراسة فلا حدَّ أدنى له؛ والحدُّ الأدنى لما بعده (يوم النقل).
        first = None if not spans and not any(spans.values()) else enrolled_at
        spans.setdefault(class_id, []).append((first, left_at))
    rows = (
        Session.objects.filter(
            school=school, class_group_id__in=list(spans), date__gte=start, date__lte=end
        )
        .exclude(status="cancelled")
        .values_list("class_group_id", "date", "start_time")
        .distinct()
    )
    return {
        (date, start_time)
        for class_id, date, start_time in rows
        if any(
            (first is None or first <= date) and (last is None or date <= last)
            for first, last in spans[class_id]
        )
    }
