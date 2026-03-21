"""
assessments/querysets.py — Custom QuerySets للتقييمات والدرجات
===============================================================
"""
from __future__ import annotations

from django.db.models import Avg, Count, F, FloatField, Q, QuerySet, Sum
from django.db.models.functions import Cast


class SubjectResultQuerySet(QuerySet):
    """QuerySet لـ StudentSubjectResult."""

    def for_student(self, student) -> "SubjectResultQuerySet":
        return self.filter(student=student)

    def for_class(self, class_group) -> "SubjectResultQuerySet":
        return self.filter(
            subject_setup__class_group=class_group
        )

    def for_subject(self, subject) -> "SubjectResultQuerySet":
        return self.filter(subject_setup__subject=subject)

    def semester(self, sem: str) -> "SubjectResultQuerySet":
        """sem = 'S1' أو 'S2'."""
        return self.filter(semester=sem)

    def year(self, academic_year: str) -> "SubjectResultQuerySet":
        return self.filter(subject_setup__academic_year=academic_year)

    def failed(self) -> "SubjectResultQuerySet":
        """نتائج الرسوب — إجمالي أقل من 50%."""
        return self.filter(total__lt=25)  # 50% من 50 درجة

    def passed(self) -> "SubjectResultQuerySet":
        return self.filter(total__gte=25)

    def with_details(self) -> "SubjectResultQuerySet":
        return self.select_related(
            "student",
            "subject_setup",
            "subject_setup__subject",
            "subject_setup__class_group",
            "subject_setup__teacher",
        )

    def class_average(self, class_group, semester: str = "S1") -> float | None:
        result = self.for_class(class_group).semester(semester).aggregate(
            avg=Avg("total")
        )
        return result["avg"]

    def top_students(self, class_group, semester: str = "S1", limit: int = 10):
        return (
            self.for_class(class_group)
            .semester(semester)
            .values("student__full_name", "student__national_id")
            .annotate(subject_avg=Avg("total"))
            .order_by("-subject_avg")[:limit]
        )


class AnnualResultQuerySet(QuerySet):
    """QuerySet لـ AnnualSubjectResult."""

    def for_student(self, student) -> "AnnualResultQuerySet":
        return self.filter(student=student)

    def for_class(self, class_group) -> "AnnualResultQuerySet":
        return self.filter(subject_setup__class_group=class_group)

    def year(self, academic_year: str) -> "AnnualResultQuerySet":
        return self.filter(subject_setup__academic_year=academic_year)

    def failed(self) -> "AnnualResultQuerySet":
        return self.filter(is_pass=False)

    def passed(self) -> "AnnualResultQuerySet":
        return self.filter(is_pass=True)

    def by_grade(self, grade: str) -> "AnnualResultQuerySet":
        """فلترة حسب التقدير: A+, A, B+, ..., F"""
        return self.filter(letter_grade=grade)

    def with_details(self) -> "AnnualResultQuerySet":
        return self.select_related(
            "student",
            "subject_setup__subject",
            "subject_setup__class_group",
        )

    def class_ranking(self, class_group, academic_year: str):
        """ترتيب الطلاب داخل الفصل حسب المتوسط السنوي."""
        return (
            self.for_class(class_group)
            .year(academic_year)
            .values("student__id", "student__full_name")
            .annotate(annual_avg=Avg("final_score"))
            .order_by("-annual_avg")
        )

    def fail_summary_by_subject(self, class_group, academic_year: str):
        """ملخص الرسوب لكل مادة."""
        return (
            self.for_class(class_group)
            .year(academic_year)
            .values("subject_setup__subject__name")
            .annotate(
                fail_count=Count("id", filter=Q(is_pass=False)),
                pass_count=Count("id", filter=Q(is_pass=True)),
                avg_score=Avg("final_score"),
            )
            .order_by("-fail_count")
        )


class AssessmentGradeQuerySet(QuerySet):
    """QuerySet لـ StudentAssessmentGrade."""

    def for_student(self, student) -> "AssessmentGradeQuerySet":
        return self.filter(student=student)

    def for_assessment(self, assessment) -> "AssessmentGradeQuerySet":
        return self.filter(assessment=assessment)

    def absent(self) -> "AssessmentGradeQuerySet":
        return self.filter(is_absent=True)

    def excused(self) -> "AssessmentGradeQuerySet":
        return self.filter(is_excused=True)

    def submitted(self) -> "AssessmentGradeQuerySet":
        return self.filter(is_absent=False, is_excused=False)

    def with_details(self) -> "AssessmentGradeQuerySet":
        return self.select_related(
            "student",
            "assessment",
            "assessment__subject_setup__subject",
        )
