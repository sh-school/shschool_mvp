"""تقريرُ فرق الأرقام لو سُوِّي المعلَّق — **قراءةٌ فقط** (D-271م، S3): لا يكتب شيئاً ولا يرسل، ولا أسماء ولا معرّفات طلبة في المخرج.

يجيب المالكَ قبل التطبيق: لو سُوِّيت الإدخالاتُ المعلَّقةُ في أجنحة الرصد النهائيّ ضمن نافذةٍ ما، فكم صفَّ غيابٍ/تأخّرٍ/حضورٍ يُضاف إلى `StudentAttendance`؟
وكم طالباً مميّزاً يتغيّر موقفُه (أيّام الغياب بلا عذر)؟ وكم طالباً يبلغ عتبةً (5/8/11/15) فتُنشأ له تنبيهاتٌ «محجوزة»؟ موزَّعاً بحسب اليوم والجناح.

الحكمُ نفسُه الذي تحسبه المنصّة (`absence_standing._judge`) لا حكمٌ ثانٍ: يُبنى خريطةُ الأيّام من الصفوف القائمة **بعد استبدال ما سيُكتب فوقه** ثمّ تُحكم.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Any

from django.utils import timezone

from core.academic_calendar import academic_year_window
from core.models import StudentEnrollment
from operations.absence_policy import gates_for
from operations.absence_standing import ATTENDED, _judge
from operations.attendance_entries import pending_direct_entries
from operations.attendance_policy import is_special_education
from operations.models import AbsenceAlert, Session, StudentAttendance
from operations.services import AttendanceService


def _new_day(scheduled: set) -> dict:
    return {
        "scheduled": set(scheduled),
        "recorded": set(),
        "attended": set(),
        "unexcused": set(),
        "excused": set(),
    }


def _unexcused_days(rows: list[tuple], scheduled: dict) -> int:
    """أيّامُ الغياب بلا عذرٍ من صفوفٍ `(تاريخ، بدء، حالة، عذر)` وخاناتٍ مجدولةٍ `{تاريخ: {بدء}}` — بحكم `_judge` نفسِه."""
    days: dict = {}
    for date, start_time, status, excuse in rows:
        day = days.setdefault(date, _new_day(scheduled.get(date, ())))
        day["scheduled"].add(start_time)
        day["recorded"].add(start_time)
        if status in ATTENDED:
            day["attended"].add(start_time)
        elif status == "absent":
            day["excused" if excuse else "unexcused"].add(start_time)
    for date, starts in scheduled.items():
        days.setdefault(date, _new_day(starts))["scheduled"] |= starts
    for day in days.values():
        day["unexcused"] -= day["attended"]
        day["excused"] -= day["attended"] | day["unexcused"]
    return sum(1 for day in days.values() if _judge(day) == "absent_unexcused")


def _due_gates(grade: Any, ese: bool, unexcused: int) -> set[str]:
    margin = AttendanceService.GATE_WARNING_MARGIN_DAYS
    return {
        gate.key
        for gate in gates_for(grade, ese)
        if unexcused > gate.max_days or gate.max_days - unexcused <= margin
    }


def diff_report(
    school: Any, *, since: dt.date | None = None, until: dt.date | None = None
) -> dict[str, Any]:
    """الفرقُ المتوقَّعُ لو سُوِّي المعلَّقُ ضمن النافذة. قراءةٌ فقط."""
    entries, blocked = pending_direct_entries(school, since=since, until=until)
    usable = [e for e in entries if (e.session_id, e.student_id) not in blocked]

    by_status: dict[str, int] = defaultdict(int)
    by_day_wing: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int))
    )
    for entry in usable:
        by_status[entry.status] += 1
        wing_obj = entry.session.class_group.wing
        wing_code = wing_obj.code if wing_obj else ""
        by_day_wing[entry.session.date.isoformat()][wing_code][entry.status] += 1

    window = academic_year_window(school, max((e.session.date for e in usable), default=None))
    per_student: dict[Any, list] = defaultdict(list)
    for entry in usable:
        per_student[entry.student_id].append(entry)

    today = max((e.session.date for e in usable), default=timezone.localdate())
    changed = 0
    new_alerts_by_gate: dict[str, int] = defaultdict(int)
    new_alert_students: set = set()
    new_alerts_by_wing: dict[str, int] = defaultdict(int)
    if window is not None:
        start, end = window
        end = min(end, today)
        for student_id, mine in per_student.items():
            student = mine[0].student
            enrollment = StudentEnrollment.objects.current_of(student)
            grade = enrollment.class_group.grade if enrollment else None
            ese = bool(enrollment and is_special_education(enrollment.class_group))
            existing = list(
                StudentAttendance.objects.filter(
                    student_id=student_id,
                    school=school,
                    session__date__gte=start,
                    session__date__lte=end,
                ).values_list(
                    "session_id", "session__date", "session__start_time", "status", "excuse_type"
                )
            )
            scheduled: dict = defaultdict(set)
            for date, start_time in (
                Session.objects.filter(
                    school=school,
                    class_group__enrollments__student_id=student_id,
                    class_group__enrollments__is_active=True,
                    date__gte=start,
                    date__lte=end,
                )
                .exclude(status="cancelled")
                .values_list("date", "start_time")
                .distinct()
            ):
                scheduled[date].add(start_time)

            before_rows = [(d, s, st, ex) for _sid, d, s, st, ex in existing]
            replaced = {e.session_id for e in mine}
            after_rows = [(d, s, st, ex) for sid, d, s, st, ex in existing if sid not in replaced]
            after_rows += [
                (e.session.date, e.session.start_time, e.status, "")
                for e in mine
                if start <= e.session.date <= end
            ]
            before = _unexcused_days(before_rows, scheduled)
            after = _unexcused_days(after_rows, scheduled)
            if after != before:
                changed += 1
            gained = _due_gates(grade, ese, after) - _due_gates(grade, ese, before)
            if gained:
                have = set(
                    AbsenceAlert.objects.filter(
                        school=school,
                        student_id=student_id,
                        period_start=start,
                        period_end=window[1],
                    ).values_list("gate", flat=True)
                )
                gained -= have
            if gained:
                new_alert_students.add(student_id)
                wing_obj = mine[0].session.class_group.wing
                wing = wing_obj.code if wing_obj else ""
                for gate in gained:
                    new_alerts_by_gate[gate] += 1
                    new_alerts_by_wing[wing] += 1

    return {
        "window": {
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
        },
        "eligible": len(entries),
        "conflicts_skipped": len(entries) - len(usable),
        "rows_added": dict(by_status),
        "students_with_entries": len(per_student),
        "students_whose_unexcused_days_change": changed,
        "students_reaching_a_new_gate": len(new_alert_students),
        "new_held_alerts_by_gate": dict(new_alerts_by_gate),
        "new_held_alerts_by_wing": dict(new_alerts_by_wing),
        "by_day_wing_status": {
            day: {wing: dict(counts) for wing, counts in wings.items()}
            for day, wings in sorted(by_day_wing.items())
        },
    }
