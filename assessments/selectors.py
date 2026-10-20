"""قراءاتُ التقييم — طابورُ أعذار الغياب عن الاختبار (W-20261001-012)؛ القراءةُ هنا لا في العرض (حارس الطبقات)."""

from __future__ import annotations

from typing import Any

from .models import StudentAssessmentGrade


def _absence_rows(school: Any) -> Any:
    return StudentAssessmentGrade.objects.filter(school=school, is_absent=True).select_related(
        "student",
        "assessment__package__setup__class_group",
        "assessment__package__setup__subject",
    )


def pending_excuse_rows(school: Any) -> Any:
    """الغياباتُ المرصودةُ التي تنتظر قرارَ العذر، الأحدثُ أوّلاً."""
    return _absence_rows(school).filter(is_excused=False).order_by("-entered_at")


def decided_excuse_rows(school: Any, limit: int = 20) -> Any:
    """آخرُ الأعذار المقرَّرة."""
    return (
        _absence_rows(school)
        .filter(is_excused=True, excuse_decided_at__isnull=False)
        .select_related("excuse_decided_by")
        .order_by("-excuse_decided_at")[:limit]
    )
