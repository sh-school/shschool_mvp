"""النوعُ التجريبيُّ لعقد التصدير الجدوليّ (`core.exports.table`): كشفُ الطلاب بنطاق الدور (W-20261109-001).

`roster_rows(user, params)` هو المحدِّدُ الواحدُ الذي تستعمله الصفحةُ والتصديرُ معاً. النطاق:

* القيادةُ وأهلُ الرعاية: طلبةُ المدرسة كلُّهم.
* مشرفُ الجناح: طلبةُ جناحه وحدَهم (`wings.scope`).
* المعلّمُ: من يُدرّسهم (جدولُ الحصص).
* غيرُهم: لا أحد — الفشلُ مغلقٌ.

الرقمُ الشخصيُّ لا يدخل الأعمدة: قائمةٌ جماعيّةٌ بالأسماء.
"""

from __future__ import annotations

from typing import Any

from core.academic_calendar import academic_year_for_school
from core.exports.table import Column, Row, TableSpec
from core.models.academic import StudentEnrollment
from core.privacy import may_search_id_partially
from student_info.access import MODULE_ROLES, sees_whole_school, taught_class_ids

from .selectors import student_register

KIND = "student_affairs.roster"

COLUMNS = (
    Column("full_name", "الاسم الكامل"),
    Column("grade", "الصف"),
    Column("section", "الشعبة"),
    Column("wing", "الجناح"),
)


def visible_student_ids(user: Any, school: Any, year: str) -> set[Any] | None:
    """معرّفاتُ الطلبة الذين يراهم هذا المستخدم؛ `None` = بلا قيد (المدرسةُ كلُّها)."""
    if sees_whole_school(user):
        return None
    if user.get_role() not in MODULE_ROLES:
        return set()
    from wings.scope import student_scope

    scope = student_scope(user, school)
    if scope.is_wing_bound:
        return set(scope.student_ids())
    return set(
        StudentEnrollment.objects.filter(
            is_active=True,
            class_group__school=school,
            class_group__academic_year=year,
            class_group_id__in=taught_class_ids(user, year),
        ).values_list("student_id", flat=True)
    )


def roster_rows(user: Any, params: Any) -> list[Row]:
    """كلُّ الصفوف بعد الفلتر ونطاق الدور — لا صفحةَ الترقيم؛ بترتيب الاسم (يفرزه العقدُ بالجناح بعدها)."""
    school = user.get_school()
    if school is None:
        return []
    year = academic_year_for_school(school)
    students, enrollment = student_register(
        school, year, params, partial_id=may_search_id_partially(user)
    )
    allowed = visible_student_ids(user, school, year)
    wings = {
        row["student_id"]: row
        for row in StudentEnrollment.objects.filter(
            is_active=True, class_group__school=school, class_group__academic_year=year
        ).values("student_id", "class_group__wing__order", "class_group__wing__name")
    }
    rows: list[Row] = []
    for member in students:
        if allowed is not None and member.user_id not in allowed:
            continue
        enr = enrollment.get(member.user_id, {})
        wing = wings.get(member.user_id, {})
        rows.append(
            {
                "full_name": member.user.full_name,
                "grade": enr.get("class_group__grade", "—"),
                "section": enr.get("class_group__section", "—"),
                "wing": wing.get("class_group__wing__name") or "—",
                "wing_order": wing.get("class_group__wing__order"),
            }
        )
    return rows


ROSTER = TableSpec(
    kind=KIND,
    title="كشف الطلاب",
    columns=COLUMNS,
    rows_for=roster_rows,
    module="students",
)
