"""جداولُ السلوك على عقد التصدير المركزيّ (W-20261109-006): التقريرُ اليوميّ والإحصاءاتُ وملفُّ الطالب.

لكلّ جدولٍ **محدِّدٌ واحدٌ** تقرأ به الصفحةُ ويقرأ به Excel وPDF: نطاقُ الدور ثمّ الفلترُ كاملاً؛ والعمودُ «م» وفرزُ الجناح
والأعمدةُ المخفيّةُ من العقد. لا وصفَ مخالفةٍ ولا رقمَ شخصيّاً ولا وليَّ أمرٍ في الملفّات (كشوفٌ جماعيّة).
"""

from __future__ import annotations

from functools import partial
from typing import Any

from django.core.exceptions import PermissionDenied
from django.http import Http404

from core.exports import registry
from core.exports.contract import Column, TableSpec, register_table

from .selectors import daily_report


def daily_rows(user: Any, params: Any) -> list[dict[str, Any]]:
    """صفوفُ التقرير السلوكيّ اليوميّ بنطاق صاحب الطلب ومرشِّحَي الجناح والصفّ، مفروزةً بالجناح."""
    return daily_report(user.get_school(), user, params)["rows"]


def statistics_rows(user: Any, params: Any) -> list[dict[str, Any]]:
    """سطورُ إحصاء السلوك كلُّها (القسم، البند، العدد) بترتيب الشاشة؛ لا طلبةَ فيها فلا فرزَ بالجناح."""
    from reports.export_builders import _behavior_statistics_sections

    from .services import behavior_statistics_data

    data = behavior_statistics_data(user.get_school(), user, params)
    return [
        {"section": heading, "label": row["label"], "count": row["count"]}
        for heading, rows in _behavior_statistics_sections(data)
        for row in rows
    ]


def profile_rows(user: Any, params: Any) -> list[dict[str, Any]]:
    """مخالفاتُ طالبٍ واحدٍ (`?student=`) كما يعرضها ملفُّه — ومن لا يبلغه نطاقُه يُمنع."""
    from core.models import CustomUser
    from core.permissions import teacher_can_access_student
    from wings.scope import student_scope

    school = user.get_school()
    student = CustomUser.objects.filter(
        id=params.get("student") or None,
        memberships__school=school,
        memberships__is_active=True,
    ).first()
    if student is None:
        raise Http404("الطالب غير موجود")
    scope = student_scope(user, school)
    if scope.is_wing_bound:
        scope.require_student(student.id)
    elif not teacher_can_access_student(user, student.id):
        raise PermissionDenied
    from .services import BehaviorService

    infractions = BehaviorService.get_student_profile(student)["infractions"]
    return [
        {
            "date": inf.date.isoformat() if inf.date else "—",
            "violation": inf.violation_category.name_ar if inf.violation_category else "—",
            "level": inf.get_level_display(),
            "step": inf.get_escalation_step_display(),
            "resolved": "نعم" if inf.is_resolved else "لا",
            "reporter": inf.reported_by.full_name if inf.reported_by else "—",
        }
        for inf in infractions
    ]


DAILY_TABLE = TableSpec(
    kind="behavior.daily_xlsx",
    title="تقرير السلوك اليومي",
    capability="behavior.statistics",
    columns=(
        Column("student", "الطالب"),
        Column("class_label", "الشعبة"),
        Column("violation", "المخالفة"),
        Column("level", "الدرجة"),
        Column("step", "الخطوة"),
        Column("reporter", "الراصد"),
    ),
    rows_for=daily_rows,
    file_module="behavior_daily",
)
STATISTICS_TABLE = TableSpec(
    kind="behavior.statistics_xlsx",
    title="إحصاءات السلوك",
    capability="behavior.statistics",
    columns=(Column("section", "القسم"), Column("label", "البند"), Column("count", "العدد")),
    rows_for=statistics_rows,
    wing_key=None,
    file_module="behavior_statistics",
)
PROFILE_TABLE = TableSpec(
    kind="behavior.student_profile_xlsx",
    title="الملف السلوكي للطالب",
    capability="behavior.view",
    columns=(
        Column("date", "التاريخ"),
        Column("violation", "المخالفة"),
        Column("level", "الدرجة"),
        Column("step", "الخطوة"),
        Column("resolved", "محلولة"),
        Column("reporter", "الراصد"),
    ),
    rows_for=profile_rows,
    wing_key=None,
    file_module="behavior_profile",
)

BEHAVIOR_TABLES = (DAILY_TABLE, STATISTICS_TABLE, PROFILE_TABLE)


def register_behavior_tables() -> None:
    """يسجّل جداولَ السلوك (Excel) وPDF اليوميّ في السجلّ المركزيّ — من `BehaviorConfig.ready()`."""
    from student_affairs.export_builders import build_table_pdf

    for table in BEHAVIOR_TABLES:
        register_table(table)
    registry.register(
        "behavior.daily_pdf",
        build=partial(
            build_table_pdf,
            DAILY_TABLE,
            ("مخالفات اليوم", "المخالفات السلوكية", "لا مخالفات في هذا اليوم"),
        ),
        capability=DAILY_TABLE.capability,
    )
