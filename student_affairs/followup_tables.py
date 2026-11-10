"""جداولُ المتابعة على عقد التصدير المركزيّ (W-20261109-006): الحضورُ والسلوكُ والتأخّرُ والأنشطةُ والتحرّكات.

المواصفةُ هنا (الأعمدةُ والقدرةُ واسمُ الملف)، والمحدِّداتُ التي تقرأ بها الصفحةُ وExcel وPDF في `followup_selectors.py`.
"""

from __future__ import annotations

from core.exports.contract import Column, TableSpec

from .followup_selectors import (
    absence_rows,
    activity_rows,
    behavior_rows,
    movement_rows,
    tardiness_rows,
)

_NAME = Column("full_name", "الطالب")
_CLASS = Column("class_label", "الصف والشعبة")

ABSENCE_TABLE = TableSpec(
    kind="student_affairs.attendance_xlsx",
    title="أكثر الطلاب غياباً",
    capability="student_affairs.follow_up",
    columns=(_NAME, _CLASS, Column("absence_count", "أيام الغياب (30 يوماً)")),
    rows_for=absence_rows,
    file_module="attendance",
)
BEHAVIOR_TABLE = TableSpec(
    kind="student_affairs.behavior_xlsx",
    title="أكثر الطلاب مخالفات",
    capability="student_affairs.follow_up",
    columns=(_NAME, _CLASS, Column("infraction_count", "عدد المخالفات")),
    rows_for=behavior_rows,
    file_module="behavior",
)
TARDINESS_TABLE = TableSpec(
    kind="student_affairs.tardiness_xlsx",
    title="الطلاب المتأخرون",
    capability="student_affairs.follow_up",
    columns=(
        _NAME,
        _CLASS,
        Column("cumulative_late", "التكرار"),
        Column("recorded_at", "توقيت التسجيل"),
        Column("notes", "الملاحظات"),
        Column("subject", "المادة"),
        Column("has_file", "مرفق"),
    ),
    rows_for=tardiness_rows,
    file_module="tardiness",
)
ACTIVITY_TABLE = TableSpec(
    kind="student_affairs.activities_xlsx",
    title="الأنشطة والإنجازات",
    capability="student_affairs.activities",
    columns=(
        _NAME,
        Column("title", "النشاط"),
        Column("type_label", "النوع"),
        Column("scope_label", "النطاق"),
        Column("date", "التاريخ"),
    ),
    rows_for=activity_rows,
    file_module="activities",
)
MOVEMENT_TABLE = TableSpec(
    kind="student_affairs.movements_xlsx",
    title="تحرّكات الطلبة",
    capability="student_affairs.transfers",
    columns=(
        Column("date", "التاريخ"),
        _NAME,
        Column("kind_label", "الحركة"),
        Column("class_text", "الشعبة"),
        Column("from_text", "من شعبة"),
        Column("detail", "تفاصيل"),
    ),
    rows_for=movement_rows,
    file_module="movements",
)

#: الجداولُ كلُّها — تُسجَّل من `StudentAffairsConfig.ready()` ويعرفها حارسُ العقد.
FOLLOWUP_TABLES = (ABSENCE_TABLE, BEHAVIOR_TABLE, TARDINESS_TABLE, ACTIVITY_TABLE, MOVEMENT_TABLE)

#: نوعُ PDF ← (الجدول، (عنوانُ المؤشّر، عنوانُ القسم، عبارةُ الفراغ)): الجدولُ نفسُه بصفوفه نفسِها، لا استعلامٌ ثانٍ.
PDF_KINDS = {
    "student_affairs.attendance_overview_pdf": (
        ABSENCE_TABLE,
        ("طلابٌ في القائمة", "أكثر الطلاب غياباً (آخر 30 يوماً)", "لا بيانات غياب في آخر 30 يوماً"),
    ),
    "student_affairs.behavior_overview_pdf": (
        BEHAVIOR_TABLE,
        ("طلابٌ في القائمة", "أكثر الطلاب مخالفات في العام", "لا مخالفاتٍ مسجّلةً هذا العام"),
    ),
    "student_affairs.tardiness_pdf": (
        TARDINESS_TABLE,
        ("إجمالي المتأخرين", "الطلاب المتأخرون", "لا يوجد طلاب متأخرون في هذا اليوم"),
    ),
}


def register_followup_tables() -> None:
    """يسجّل جداولَ المتابعة (Excel) وملفّاتِها PDF في السجلّ المركزيّ — من `StudentAffairsConfig.ready()`."""
    from functools import partial

    from core.exports import registry
    from core.exports.contract import register_table

    from .export_builders import build_table_pdf

    for table in FOLLOWUP_TABLES:
        register_table(table)
    for kind, (table, labels) in PDF_KINDS.items():
        registry.register(
            kind, build=partial(build_table_pdf, table, labels), capability=table.capability
        )
