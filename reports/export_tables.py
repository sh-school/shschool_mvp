"""كشفُ نتائج الفصل على عقد التصدير المركزيّ (W-20261109-007): Excel وPDF من المحدِّد نفسِه (`ReportDataService.get_class_results`).

المعلّمُ لا يصدّر إلا فصولَه (SEC-04) — يُعاد الفحصُ في المحدِّد لأنّ الصلاحيّةَ قد تتغيّر بين الطلب والتنفيذ. درجاتُ المواد في عمودٍ
نصّيٍّ واحد (موادُّ الفصل تختلف من شعبةٍ لأخرى والعقدُ بأعمدةٍ ثابتة). الرقمُ الشخصيّ غيرُ موجودٍ في الملفّ.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied

from core.academic_calendar import academic_year_for_school
from core.exports.contract import Column, TableSpec, register_table
from core.models import ClassGroup

from .selectors import teacher_can_access_class
from .services import ReportDataService


def class_results_rows(user: Any, params: Any) -> list[dict[str, Any]]:
    """صفوفُ كشف النتائج بترتيب المتوسط: المدير أو المعلّمُ لفصله وحدَه."""
    school = user.get_school()
    if not (user.is_admin() or user.is_teacher()):
        raise PermissionDenied
    class_group = ClassGroup.objects.select_related("wing").get(
        id=params["class_id"], school=school
    )
    year = params.get("year") or academic_year_for_school(school)
    if not teacher_can_access_class(user, school, class_group, year):
        raise PermissionDenied
    data = ReportDataService.get_class_results(class_group, school, year)
    wing_order = getattr(class_group.wing, "order", None)
    return [
        {
            "student": row["student"].full_name,
            "grades": " · ".join(
                f"{subject.name_ar} {_grade(row['grades'].get(subject.name_ar))}"
                for subject in data["subjects"]
            ),
            "avg": row["avg"] if row["avg"] is not None else "—",
            "status": row["status"],
            "rank": row["rank"],
            "wing_order": wing_order,
        }
        for row in data["student_rows"]
    ]


def _grade(annual: Any) -> str:
    total = getattr(annual, "annual_total", None)
    return "—" if total is None else f"{float(total):g}"


CLASS_RESULTS_TABLE = TableSpec(
    kind="reports.class_results_xlsx",
    title="كشف نتائج الفصل",
    capability="reports.results",
    columns=(
        Column("student", "اسم الطالب"),
        Column("grades", "درجات المواد"),
        Column("avg", "المتوسط"),
        Column("status", "الحالة"),
        Column("rank", "الترتيب"),
    ),
    rows_for=class_results_rows,
    file_module="class_results",
)


def register_report_tables() -> None:
    """يسجّل كشفَ نتائج الفصل (Excel) في السجلّ المركزيّ — من `ReportsConfig.ready()`؛ وPDFُه صفحةُ `class_results_pdf` من المحدِّد نفسه."""
    register_table(CLASS_RESULTS_TABLE)
