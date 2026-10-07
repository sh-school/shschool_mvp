"""مسحُ عتبات الغياب بعد نهاية الدوام (قرارُ المالك 2026-10-07): إخطارُ وليّ الأمر وعتباتُ الغياب تُحسب بعد الدوام لا لحظةَ إدخال المعلّم.

كان `check_absence_threshold` لا يُستدعى من مسار الجدول أصلاً (يُستدعى من كشف الأجنحة القديم والرصد القديم وحدَهما)، فلا إنذارَ ولا إخطارَ لغيابٍ كُتب من الجدول.
والمسحُ يعدّ أيّامَ تمدرسٍ ولا يكرّر إنذاراً (`get_or_create`) فتكراره آمن، والمهمّةُ اليوميّةُ لإرسال التنبيهات (07:00) تحمل ما أُنشئ إلى وليّ الأمر صباحَ اليوم التالي.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from core.models import CustomUser

from .models import StudentAttendance

if TYPE_CHECKING:
    from core.models import School


def sweep_absence_gates(school: School, day: dt.date) -> int:
    """يفحص عتباتِ كلّ من غاب في `day` مرّةً واحدة. يعيد عددَ الطلبة المفحوصين."""
    from operations.services import AttendanceService

    ids = (
        StudentAttendance.objects.filter(session__school=school, session__date=day, status="absent")
        .values_list("student_id", flat=True)
        .distinct()
    )
    students = CustomUser.objects.filter(pk__in=list(ids))
    count = 0
    for student in students:
        AttendanceService.check_absence_threshold(student, school, on=day)
        count += 1
    return count
