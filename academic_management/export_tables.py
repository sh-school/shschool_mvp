"""التقاريرُ الأكاديميّةُ الأربعةُ على عقد التصدير المركزيّ (W-20261109-007).

المحدِّدُ واحدٌ للصفحة وExcel وPDF (`report_selectors`): الفلترُ كاملاً لا صفحةَ الترقيم، والعمودُ «م» من العقد، والأعمدةُ
المخفيّةُ تُخفى في الملفّ. لا فرزَ بالجناح: صفوفُها تقاريرُ تقييمٍ بلا جناحٍ في الصفّ (يُحجب عن مشرف الجناح أصلاً بالقدرة).
"""

from __future__ import annotations

from functools import partial
from typing import Any

from core.exports import registry
from core.exports.contract import Column, TableSpec, register_table

from . import report_selectors as sel

_CAP = "academic.reports_school"
_DASH = "—"


def _school(user: Any) -> Any:
    return user.get_school()


def quiz_rows(user: Any, params: Any) -> list[dict[str, Any]]:
    return [
        {
            **r,
            "date": r["date"].strftime("%Y/%m/%d") if r.get("date") else _DASH,
        }
        for r in sel.quiz_data(_school(user), params)["rows"]
    ]


def exam_results_rows(user: Any, params: Any) -> list[dict[str, Any]]:
    return list(sel.exam_results_data(_school(user), params)["rows"])


def progress_rows(user: Any, params: Any) -> list[dict[str, Any]]:
    return list(sel.progress_data(_school(user), params)["students"])


def monthly_rows(user: Any, params: Any) -> list[dict[str, Any]]:
    return list(sel.monthly_data(_school(user), params)["rows"])


QUIZ_TABLE = TableSpec(
    kind="academic.quiz_xlsx",
    title="تقارير الاختبارات القصيرة",
    capability=_CAP,
    columns=(
        Column("student_name", "اسم الطالب"),
        Column("subject", "المادة"),
        Column("class_group", "الفصل"),
        Column("title", "عنوان التقييم"),
        Column("date", "التاريخ"),
        Column("raw_grade", "الدرجة"),
        Column("max_grade", "من"),
        Column("pct", "النسبة %"),
    ),
    rows_for=quiz_rows,
    wing_key=None,
    file_module="academic_quiz",
)
EXAM_TABLE = TableSpec(
    kind="academic.exam_results_xlsx",
    title="تقارير نتائج الاختبارات",
    capability=_CAP,
    columns=(
        Column("package", "الباقة"),
        Column("semester", "الفصل الدراسي"),
        Column("class_group", "الشعبة"),
        Column("subject", "المادة"),
        Column("students_count", "عدد الطلاب"),
        Column("avg_score", "المتوسط"),
        Column("min_score", "الأدنى"),
        Column("max_score", "الأعلى"),
        Column("max_grade", "من"),
    ),
    rows_for=exam_results_rows,
    wing_key=None,
    file_module="academic_exam_results",
)
PROGRESS_TABLE = TableSpec(
    kind="academic.progress_xlsx",
    title="تقارير التقدم الأكاديمي",
    capability=_CAP,
    columns=(
        Column("rank", "الترتيب"),
        Column("student_name", "اسم الطالب"),
        Column("assessments_count", "عدد التقييمات"),
        Column("avg_pct", "المتوسط %"),
        Column("min_pct", "الأدنى %"),
        Column("max_pct", "الأعلى %"),
    ),
    rows_for=progress_rows,
    wing_key=None,
    file_module="academic_progress",
)
MONTHLY_TABLE = TableSpec(
    kind="academic.monthly_xlsx",
    title="التقرير السلوكي والتعليمي الشهري",
    capability=_CAP,
    columns=(
        Column("student_name", "اسم الطالب"),
        Column("quiz_count", "عدد الاختبارات"),
        Column("quiz_avg", "متوسط الاختبارات %"),
        Column("behavior_count", "عدد المخالفات"),
    ),
    rows_for=monthly_rows,
    wing_key=None,
    file_module="academic_monthly",
)

ACADEMIC_TABLES = {
    "quiz": QUIZ_TABLE,
    "exam-results": EXAM_TABLE,
    "progress": PROGRESS_TABLE,
    "monthly": MONTHLY_TABLE,
}
_PDF_LABELS = {
    "quiz": ("تقييمات", "تقارير الاختبارات القصيرة", "لا تقييمات بهذه المعايير"),
    "exam-results": ("صفوف", "تقارير نتائج الاختبارات", "لا نتائج بهذه المعايير"),
    "progress": ("طلاب", "تقارير التقدم الأكاديمي", "لا تقييمات في هذه الفترة"),
    "monthly": ("طلاب", "التقرير السلوكي والتعليمي الشهري", "لا طلاب بهذه المعايير"),
}


def pdf_kind(slug: str) -> str:
    return ACADEMIC_TABLES[slug].kind.removesuffix("_xlsx") + "_pdf"


def register_academic_tables() -> None:
    """يسجّل التقاريرَ الأربعةَ (Excel وPDF) في السجلّ المركزيّ — من `AcademicManagementConfig.ready()`."""
    from student_affairs.export_builders import build_table_pdf

    for slug, table in ACADEMIC_TABLES.items():
        register_table(table)
        registry.register(
            pdf_kind(slug),
            build=partial(build_table_pdf, table, _PDF_LABELS[slug]),
            capability=table.capability,
        )
