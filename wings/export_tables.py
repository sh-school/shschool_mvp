"""جداولُ الجناح على عقد التصدير المركزيّ (W-20261109-007): سجلُّ الجناح وتقريرُ الوزارة وأذونات الخروج.

لكلّ جدولٍ **محدِّدٌ واحدٌ** تقرأ به الصفحةُ ويقرأ به Excel وPDF: نطاقُ الدور ثمّ الفلترُ كاملاً (لا صفحةُ الترقيم وحدَها)؛
والعمودُ «م» وفرزُ الجناح والأعمدةُ المخفيّةُ من العقد. لا رقمَ شخصيّاً في الملفّات (كشوفٌ جماعيّة).
"""

from __future__ import annotations

import datetime as dt
from functools import partial
from typing import Any

from django.http import Http404
from django.utils import timezone

from core.exports import registry
from core.exports.contract import Column, TableSpec, register_table

from .ministry_selectors import ministry_rows

_MINISTRY_PDF = ("طلابٌ يُرفعون", "إحصائية الغياب", "لا غائبين في الحصّتين الأولى والثانية")
_REGISTER_PDF = ("طلابٌ في الكشف", "كشف حضور الحصص", "لا طلبة في هذا الجناح")
_PERMITS_PDF = ("أذونات اليوم", "أذونات خروج الطلاب", "لا أذوناتٍ في هذا اليوم")


def _day(params: Any) -> dt.date:
    try:
        return dt.date.fromisoformat(params.get("date") or "")
    except ValueError:
        return timezone.localdate()


def register_rows(user: Any, params: Any) -> list[dict[str, Any]]:
    """طلبةُ كشف الجناح (`?wing=<code>`) أو أجنحةِ المستخدم كلِّها: رمزُ كلّ حصّةٍ وغيابُه وتأخّرُه — بلا أرقامٍ شخصيّة."""
    from core.academic_calendar import academic_year_for_school

    from .register import wing_register
    from .services import wings_of

    school = user.get_school()
    wings = wings_of(user, school, academic_year_for_school(school))
    code = params.get("wing") or ""
    if code:
        wings = [w for w in wings if w.code == code]
        if not wings:
            raise Http404("ليس من أجنحتك")
    day = _day(params)
    rows: list[dict[str, Any]] = []
    for wing in wings:
        for section in wing_register(wing, day).sections:
            rows += [
                {
                    "class_label": section.class_group.short_code,
                    "student": row.name,
                    "marks": " ".join(mark.text for mark in row.marks),
                    "absent_periods": row.absent_periods,
                    "late_count": row.late_count,
                    "late_minutes": row.late_minutes,
                    "wing_order": wing.order,
                }
                for row in section.rows
            ]
    return rows


def exit_permit_rows(user: Any, params: Any) -> list[dict[str, Any]]:
    """أذوناتُ اليوم المعروضةُ في الصفحة (`permits_for`: نطاقُ الجناح أو ما طلبه المعلّم) صفاً لكلّ إذن."""
    from .exit_permit_services import permits_for

    permits = permits_for(user, user.get_school(), _day(params))
    return [
        {
            "sequence": p.sequence,
            "student": p.student.full_name,
            "class_label": str(p.class_group),
            "reason": p.get_reason_display() + (f" — {p.note}" if p.note else ""),
            "exit_at": timezone.localtime(p.exit_at).strftime("%H:%M"),
            "periods": p.completed_periods,
            "status": p.get_status_display(),
            "wing_order": getattr(p.class_group.wing, "order", None),
        }
        for p in permits
    ]


REGISTER_TABLE = TableSpec(
    kind="wings.register_xlsx",
    title="كشف حضور الحصص",
    capability="wings.record_day",
    columns=(
        Column("class_label", "الشعبة"),
        Column("student", "الطالب"),
        Column("marks", "الحصص (ح حاضر · غ غائب · م متأخّر)"),
        Column("absent_periods", "حصص الغياب"),
        Column("late_count", "مرّات التأخّر"),
        Column("late_minutes", "دقائق التأخّر"),
    ),
    rows_for=register_rows,
    file_module="wing_register",
)
MINISTRY_TABLE = TableSpec(
    kind="wings.ministry_table_xlsx",
    title="إحصائية الغياب",
    capability="wings.record_day",
    columns=(
        Column("grade", "الصفّ"),
        Column("class_code", "الشعبة"),
        Column("name", "الطالب"),
        Column("excused", "العذر"),
        Column("mark", "قيد الطالب"),
    ),
    rows_for=ministry_rows,
    file_module="ministry_p1p2",
)
EXIT_PERMITS_TABLE = TableSpec(
    kind="wings.exit_permits_xlsx",
    title="أذونات خروج الطلاب",
    capability="wings.exit_permit_request",
    columns=(
        Column("sequence", "الرقم"),
        Column("student", "الطالب"),
        Column("class_label", "الشعبة"),
        Column("reason", "السبب"),
        Column("exit_at", "الخروج"),
        Column("periods", "الحصص"),
        Column("status", "الحالة"),
    ),
    rows_for=exit_permit_rows,
    file_module="exit_permits",
)

WINGS_TABLES = (REGISTER_TABLE, MINISTRY_TABLE, EXIT_PERMITS_TABLE)

#: نوعُ PDF ← (الجدول، (عنوانُ المؤشّر، عنوانُ القسم، عبارةُ الفراغ)): الجدولُ نفسُه بصفوفه نفسِها، لا استعلامٌ ثانٍ.
PDF_KINDS = {
    "wings.register_pdf": (REGISTER_TABLE, _REGISTER_PDF),
    "wings.ministry_table_pdf": (MINISTRY_TABLE, _MINISTRY_PDF),
    "wings.exit_permits_pdf": (EXIT_PERMITS_TABLE, _PERMITS_PDF),
}


def register_wings_tables() -> None:
    """يسجّل جداولَ الجناح (Excel) وملفّاتِها PDF في السجلّ المركزيّ — من `WingsConfig.ready()`."""
    from student_affairs.export_builders import build_table_pdf

    for table in WINGS_TABLES:
        register_table(table)
    for kind, (table, labels) in PDF_KINDS.items():
        registry.register(
            kind, build=partial(build_table_pdf, table, labels), capability=table.capability
        )
