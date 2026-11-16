"""جدولا حضور الموظفين على عقد التصدير المركزيّ (W-20261110-004): تقريرُ الشهر وكشفُ اليوم.

لكلّ جدولٍ **محدِّدٌ واحدٌ** تقرأ به الصفحةُ وExcel: نطاقُ القارئ (`viewer`) ثمّ ترشيحُ الشاشة كاملاً — والعمودُ «م»
والأعمدةُ المخفيّةُ من العقد. الموظّفون بلا أجنحةٍ فلا فرزَ بالجناح (`wing_key=None`)، وتُفرز الصفوفُ بالاسم كما تعرضها
الشاشة. الرقمُ الوظيفيّ وحدَه؛ لا رقمَ شخصيّاً، ولا نصَّ عذرٍ (م-7).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.core.exceptions import PermissionDenied
from django.utils import timezone
from django.utils.dateparse import parse_date

from core.exports.contract import Column, TableSpec, register_table

from .attendance import StaffAttendanceService
from .attendance.rules import ABSENCE_TYPES, STATUS_LABELS, STATUSES

_NOT_MARKED = "لم يُرصد"


def month_of(params: Any) -> tuple[int, int]:
    """«YYYY-MM» من `month` — والشهرُ الحاضرُ لما فسد."""
    try:
        year, month = (int(part) for part in str(params.get("month") or "").split("-"))
        dt.date(year, month, 1)
    except ValueError:
        today = timezone.localdate()
        return today.year, today.month
    return year, month


def day_of(params: Any) -> dt.date:
    """اليومُ من `date` — واليومُ الحاضرُ لما غاب أو فسد أو جاوز اليوم."""
    today = timezone.localdate()
    parsed = parse_date(str(params.get("date") or ""))
    return parsed if parsed and parsed <= today else today


def monthly_rows(user: Any, params: Any) -> list[dict[str, Any]]:
    """صفوفُ تقرير الشهر لمن يراهم القارئ — هي نفسُها صفوفُ الصفحة."""
    year, month = month_of(params)
    report = StaffAttendanceService.monthly_report(user.get_school(), year, month, viewer=user)
    return [dict(row) for row in report["rows"]]


def daily_rows(user: Any, params: Any) -> list[dict[str, Any]]:
    """صفوفُ كشف اليوم لمن تفتح له اللوحةُ، بعد بحث الاسم والحالة (`q` و`status`) كما في الشاشة."""
    school = user.get_school()
    if not StaffAttendanceService.can_open_board(school, user):
        raise PermissionDenied("كشفُ اليوم لمن تفتح له لوحةُ الرصد")
    absence_labels = dict(ABSENCE_TYPES)
    needle = str(params.get("q") or "").strip()[:80].casefold()
    state = str(params.get("status") or "")
    rows: list[dict[str, Any]] = []
    for item in StaffAttendanceService.daily_board(school, day_of(params), viewer=user)["rows"]:
        staff, record = item["staff"], item["record"]
        if needle and needle not in f"{staff.full_name} {staff.employee_number or ''}".casefold():
            continue
        if state and (record.status if record else "unmarked") != state:
            continue
        rows.append(
            {
                "employee_number": staff.employee_number or "",
                "full_name": staff.full_name,
                "status": STATUS_LABELS.get(record.status, record.status)
                if record
                else _NOT_MARKED,
                "check_in": f"{record.check_in:%H:%M}" if record and record.check_in else "",
                "check_out": f"{record.check_out:%H:%M}" if record and record.check_out else "",
                "late_minutes": record.late_minutes if record else "",
                "early_leave_minutes": record.early_leave_minutes if record else "",
                "permit_minutes": record.permit_minutes if record else "",
                "absence_type": absence_labels.get(record.absence_type, "")
                if record and record.absence_type
                else "",
            }
        )
    return rows


MONTHLY_TABLE = TableSpec(
    kind="staff_affairs.attendance_month_table",
    title="حضور الموظفين — تقرير الشهر",
    capability="staff_affairs.attendance_report",
    columns=(
        Column("employee_number", "الرقم الوظيفي"),
        Column("full_name", "الاسم"),
        *(Column(key, STATUS_LABELS[key]) for key in STATUSES),
        Column("absent_uncovered", "غياب غير مغطّى"),
        Column("covered_late", "غياب غُطّي بعد المهلة"),
        *(Column(f"absence_{key}", f"غياب: {label}") for key, label in ABSENCE_TYPES),
        Column("late_minutes", "دقائق التأخّر"),
        Column("early_leave_minutes", "دقائق الانصراف المبكر بلا إذن"),
        Column("permit_minutes", "دقائق الإذن المعتمد"),
        Column("permit_remaining", "المتبقّي من سقف الأذونات"),
        Column("exception_days", "أيام الاستثناء (نموذج 03)"),
    ),
    rows_for=monthly_rows,
    wing_key=None,
    file_module="staff_attendance_month",
)
DAILY_TABLE = TableSpec(
    kind="staff_affairs.attendance_day_table",
    title="حضور الموظفين — كشف اليوم",
    capability="staff_affairs.attendance_record",
    columns=(
        Column("employee_number", "الرقم الوظيفي"),
        Column("full_name", "الاسم"),
        Column("status", "الحالة"),
        Column("check_in", "وقت الحضور"),
        Column("check_out", "وقت الانصراف"),
        Column("late_minutes", "دقائق التأخّر"),
        Column("early_leave_minutes", "دقائق الانصراف المبكر بلا إذن"),
        Column("permit_minutes", "دقائق الإذن المعتمد"),
        Column("absence_type", "نوع الغياب"),
    ),
    rows_for=daily_rows,
    wing_key=None,
    file_module="staff_attendance_day",
)

STAFF_TABLES = (MONTHLY_TABLE, DAILY_TABLE)


def register_staff_tables() -> None:
    """يسجّل جدولَي حضور الموظفين في عقد التصدير — من `StaffAffairsConfig.ready()`."""
    for table in STAFF_TABLES:
        register_table(table)
