"""مسحُ عتبات الغياب بعد نهاية الدوام (قرارُ المالك 2026-10-07): عتباتُ الغياب تُحسب بعد الدوام لا لحظةَ إدخال المعلّم.

كان `check_absence_threshold` لا يُستدعى من مسار الجدول أصلاً (يُستدعى من كشف الأجنحة القديم والرصد القديم وحدَهما)، فلا إنذارَ لغيابٍ كُتب من الجدول.
والمسحُ يعدّ أيّامَ تمدرسٍ ولا يكرّر إنذاراً (`get_or_create`) فتكراره آمن. **ولا يُرسَل لوليّ الأمر شيءٌ (D-246م):** التنبيهاتُ تُنشأ «محجوزة» ويُصدرها حاصرُ الغياب بزرّه.
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
        AttendanceService.raise_absence_alerts(student, school, on=day)
        count += 1
    return count


def absent_students_on(school: School, day: dt.date):
    """طلبةُ المدرسة الذين لهم غيابٌ مرصودٌ في `day` (مميَّزون)."""
    ids = (
        StudentAttendance.objects.filter(session__school=school, session__date=day, status="absent")
        .values_list("student_id", flat=True)
        .distinct()
    )
    return CustomUser.objects.filter(pk__in=list(ids))


def would_create(school: School, day: dt.date) -> int:
    """كم تنبيهاً «محجوزاً» سيُنشئه مسحُ `day` الآن؟ — قراءةٌ فقط: يحسب الموقفَ والعتباتِ المستحقّةَ ويطرح الموجودَ، ولا يكتب شيئاً."""
    from core.academic_calendar import academic_year_window
    from core.models import StudentEnrollment
    from operations.absence_policy import gates_for
    from operations.absence_standing import standing_for
    from operations.models import AbsenceAlert
    from operations.services import AttendanceService

    window = academic_year_window(school, day)
    if window is None:
        return 0
    margin = AttendanceService.GATE_WARNING_MARGIN_DAYS
    total = 0
    for student in absent_students_on(school, day):
        enrollment = StudentEnrollment.objects.current_of(student)
        grade = enrollment.class_group.grade if enrollment else None
        if not gates_for(grade):
            continue
        standing = standing_for(student, school, grade=grade, on=day)
        for gate in standing.gates:
            due = (
                standing.unexcused_days > gate.max_days
                or gate.max_days - standing.unexcused_days <= margin
            )
            if (
                due
                and not AbsenceAlert.objects.filter(
                    school=school,
                    student=student,
                    gate=gate.key,
                    period_start=window[0],
                    period_end=window[1],
                ).exists()
            ):
                total += 1
    return total
