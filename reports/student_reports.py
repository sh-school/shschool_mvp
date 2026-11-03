"""تقارير الطلاب الجماعيّة (W-20261101-008): تقريرُ كلّ طالبٍ في قائمةٍ بعددِ استعلاماتٍ ثابت.

استُخرجت من `ReportDataService` لتبقى `services.py` ضمن حدّ الحجم؛ و`get_students_reports` يفوّض إليها.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Count, Q
from django.utils import timezone

from assessments.models import AnnualSubjectResult, StudentSubjectResult
from core.academic_calendar import academic_year_for_school
from core.models import StudentEnrollment
from core.verdict_read import failing_statuses, passing_statuses
from operations.models import StudentAttendance

if TYPE_CHECKING:
    from core.models import CustomUser, School


def build_students_reports(
    students: list[CustomUser],
    school: School,
    year: str | None = None,
) -> list[dict]:
    """تقريرُ كلّ طالبٍ في القائمة بالترتيب نفسِه — بعددِ استعلاماتٍ ثابتٍ لا يتبع عددَ الطلاب.

    كان `get_student_report` يُشغَّل لكلّ طالبٍ في «شهادات الفصل» (≈11 استعلاماً × 22 طالباً = 240):
    فصارت النتائجُ السنويّةُ والفصليّةُ والقيدُ والحضورُ تُجلب دفعةً واحدةً وتُوزَّع بمفتاح الطالب.
    """
    year = year or academic_year_for_school(school)
    student_ids = [student.pk for student in students]
    today = timezone.now().date()

    annuals_by_student: dict = {pk: [] for pk in student_ids}
    for ann in (
        AnnualSubjectResult.objects.filter(
            student_id__in=student_ids, school=school, academic_year=year
        )
        .select_related("setup__subject")
        .order_by("setup__subject__name_ar")
    ):
        annuals_by_student[ann.student_id].append(ann)

    semester_maps: dict = {pk: {"S1": {}, "S2": {}} for pk in student_ids}
    for res in StudentSubjectResult.objects.filter(
        student_id__in=student_ids, school=school, semester__in=("S1", "S2")
    ):
        semester_maps[res.student_id][res.semester][res.setup_id] = res

    enrollments: dict = {}
    for enr in (
        StudentEnrollment.objects.filter(student_id__in=student_ids, is_active=True)
        .select_related("class_group")
        .newest_first()
    ):
        enrollments.setdefault(enr.student_id, enr)

    attendance = {
        row["student_id"]: row
        for row in StudentAttendance.objects.filter(
            student_id__in=student_ids,
            session__school=school,
            session__class_group__academic_year=year,
        )
        .values("student_id")
        .annotate(
            absent=Count("pk", filter=Q(status="absent")),
            late=Count("pk", filter=Q(status="late")),
        )
    }

    passing = passing_statuses()
    failing = failing_statuses()
    reports = []
    for student in students:
        annual = annuals_by_student[student.pk]
        s1_map = semester_maps[student.pk]["S1"]
        s2_map = semester_maps[student.pk]["S2"]
        grades = [float(r.annual_total) for r in annual if r.annual_total is not None]
        counts = attendance.get(student.pk, {})
        reports.append(
            {
                "student": student,
                "school": school,
                "year": year,
                "enrollment": enrollments.get(student.pk),
                "rows": [
                    {
                        "subject": ann.setup.subject.name_ar,
                        "s1": s1_map.get(ann.setup_id),
                        "s2": s2_map.get(ann.setup_id),
                        "annual": ann,
                    }
                    for ann in annual
                ],
                "total": len(annual),
                "passed": sum(1 for r in annual if r.status in passing),
                "failed": sum(1 for r in annual if r.status in failing),
                "avg": round(sum(grades) / len(grades), 2) if grades else None,
                "absent_total": counts.get("absent", 0),
                "late_total": counts.get("late", 0),
                "print_date": today,
            }
        )
    return reports
