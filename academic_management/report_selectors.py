"""محدِّداتُ التقارير الأكاديميّة الأربعة: معاملاتُ الرابط ← بياناتُ التقرير — تقرأ بها الصفحةُ والتصديرُ معاً (W-20261109-007).

لا اشتقاقَ ثانياً للمعاملات: ما تعرضه الشاشةُ بعد الفلترة هو ما يخرج في الملفّ (عقدُ التصدير المركزيّ).
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from reports.services import AcademicReportsService


def parse_int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def quiz_data(school: Any, params: Any) -> dict[str, Any]:
    return AcademicReportsService.get_quiz_reports(
        school,
        subject_id=params.get("subject_id") or None,
        class_group_id=params.get("class_group_id") or None,
        student_id=params.get("student_id") or None,
        date_from=params.get("date_from") or None,
        date_to=params.get("date_to") or None,
    )


def exam_results_data(school: Any, params: Any) -> dict[str, Any]:
    return AcademicReportsService.get_exam_results_reports(
        school,
        package_type=params.get("package_type") or None,
        semester=params.get("semester") or None,
        class_group_id=params.get("class_group_id") or None,
    )


def progress_data(school: Any, params: Any) -> dict[str, Any]:
    return AcademicReportsService.get_academic_progress_reports(
        school,
        class_group_id=params.get("class_group_id") or None,
        date_from=params.get("date_from") or None,
        date_to=params.get("date_to") or None,
    )


def monthly_data(school: Any, params: Any) -> dict[str, Any]:
    """التقريرُ الشهريّ: شهرٌ وسنةٌ مقبولان وإلّا فالحاليّان."""
    now = timezone.now()
    month = parse_int(params.get("month"), now.month)
    year = parse_int(params.get("year"), now.year)
    if month is None or not (1 <= month <= 12):
        month = now.month
    if year is None or not (2000 <= year <= 2100):
        year = now.year
    return AcademicReportsService.get_monthly_behavior_academic_report(
        school,
        month=month,
        year=year,
        scope=params.get("scope", "section"),
        class_group_id=params.get("class_group_id") or None,
        student_id=params.get("student_id") or None,
    )
