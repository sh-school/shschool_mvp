"""
parents/services.py
━━━━━━━━━━━━━━━━━━
Business logic لبوابة ولي الأمر
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.db.models import Count, Q, Sum
from django.utils import timezone

from assessments.models import AnnualSubjectResult, StudentSubjectResult
from core.models import ParentStudentLink, StudentEnrollment
from operations.models import StudentAttendance

if TYPE_CHECKING:
    from core.models import CustomUser, School


class ParentService:
    @staticmethod
    def get_children_data(
        user: CustomUser,
        school: School,
        year: str = settings.CURRENT_ACADEMIC_YEAR,
    ) -> list:
        """
        يعيد قائمة بأبناء ولي الأمر مع إحصائيات كل طالب.
        كل عنصر: {link, student, enrollment, total_subj, passed,
                   failed, incomplete, absent_30, late_30}
        """
        links = (
            ParentStudentLink.objects.filter(parent=user, school=school)
            .select_related("student")
            .order_by("student__full_name")
        )
        since = timezone.now().date() - timedelta(days=30)

        student_ids = [link.student_id for link in links]

        # Bulk: enrollments keyed by student_id
        enrollments_map: dict = {}
        for enr in (
            StudentEnrollment.objects.filter(student_id__in=student_ids, is_active=True)
            .select_related("class_group")
        ):
            enrollments_map.setdefault(enr.student_id, enr)

        # Bulk: annual result counts per student
        annual_counts = (
            AnnualSubjectResult.objects.filter(
                student_id__in=student_ids, school=school, academic_year=year
            )
            .values("student_id")
            .annotate(
                total_subj=Count("id"),
                passed=Count("id", filter=Q(status="pass")),
                failed=Count("id", filter=Q(status="fail")),
                incomplete=Count("id", filter=Q(status="incomplete")),
            )
        )
        annual_map = {row["student_id"]: row for row in annual_counts}

        # Bulk: attendance counts per student (last 30 days)
        att_counts = (
            StudentAttendance.objects.filter(
                student_id__in=student_ids,
                session__school=school,
                session__date__gte=since,
            )
            .values("student_id")
            .annotate(
                absent_30=Count("id", filter=Q(status="absent")),
                late_30=Count("id", filter=Q(status="late")),
            )
        )
        att_map = {row["student_id"]: row for row in att_counts}

        children: list = []
        for link in links:
            student = link.student
            sid = student.pk
            ann = annual_map.get(sid, {})
            att = att_map.get(sid, {})

            children.append(
                {
                    "link": link,
                    "student": student,
                    "enrollment": enrollments_map.get(sid),
                    "total_subj": ann.get("total_subj", 0),
                    "passed": ann.get("passed", 0),
                    "failed": ann.get("failed", 0),
                    "incomplete": ann.get("incomplete", 0),
                    "absent_30": att.get("absent_30", 0),
                    "late_30": att.get("late_30", 0),
                }
            )

        return children

    @staticmethod
    def get_student_grades(
        student: CustomUser,
        school: School,
        year: str = settings.CURRENT_ACADEMIC_YEAR,
    ) -> dict:
        """ملخص الدرجات لطالب"""
        annual = (
            AnnualSubjectResult.objects.filter(student=student, school=school, academic_year=year)
            .select_related("setup__subject", "setup__class_group")
            .order_by("setup__subject__name_ar")
        )

        s1_map = {
            r.setup_id: r
            for r in StudentSubjectResult.objects.filter(
                student=student, school=school, semester="S1"
            ).select_related("setup__subject")
        }
        s2_map = {
            r.setup_id: r
            for r in StudentSubjectResult.objects.filter(
                student=student, school=school, semester="S2"
            ).select_related("setup__subject")
        }

        rows = [
            {
                "subject": ann.setup.subject.name_ar,
                "s1": s1_map.get(ann.setup_id),
                "s2": s2_map.get(ann.setup_id),
                "annual": ann,
            }
            for ann in annual
        ]

        grades = [float(r.annual_total) for r in annual if r.annual_total]
        avg = round(sum(grades) / len(grades), 1) if grades else None

        return {
            "annual_results": annual,
            "rows": rows,
            "total": annual.count(),
            "passed": annual.filter(status="pass").count(),
            "failed": annual.filter(status="fail").count(),
            "avg": avg,
        }

    @staticmethod
    def get_student_attendance(
        student: CustomUser, school: School, days: int = 30
    ) -> dict:
        """ملخص الغياب لطالب خلال فترة"""
        since = timezone.now().date() - timedelta(days=days)

        attendance = (
            StudentAttendance.objects.filter(
                student=student,
                session__school=school,
                session__date__gte=since,
            )
            .select_related("session__subject", "session__class_group")
            .order_by("-session__date", "session__start_time")
        )

        by_date: dict = {}
        for att in attendance:
            d = att.session.date
            if d not in by_date:
                by_date[d] = {"date": d, "records": [], "has_absent": False, "has_late": False}
            by_date[d]["records"].append(att)
            if att.status == "absent":
                by_date[d]["has_absent"] = True
            if att.status == "late":
                by_date[d]["has_late"] = True

        total = attendance.count()
        absent = attendance.filter(status="absent").count()
        late = attendance.filter(status="late").count()
        present = attendance.filter(status="present").count()

        return {
            "days_list": sorted(by_date.values(), key=lambda x: x["date"], reverse=True),
            "total": total,
            "present": present,
            "absent": absent,
            "late": late,
            "att_pct": round(present / total * 100) if total else 0,
            "since": since,
        }
