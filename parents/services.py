"""
parents/services.py
━━━━━━━━━━━━━━━━━━
Business logic لبوابة ولي الأمر
"""

from django.conf import settings

from datetime import timedelta

from django.utils import timezone

from assessments.models import AnnualSubjectResult, StudentSubjectResult
from core.models import ParentStudentLink, StudentEnrollment
from operations.models import StudentAttendance


class ParentService:
    @staticmethod
    def get_children_data(user, school, year=settings.CURRENT_ACADEMIC_YEAR):
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
        children = []

        for link in links:
            student = link.student
            enrollment = (
                StudentEnrollment.objects.filter(student=student, is_active=True)
                .select_related("class_group")
                .first()
            )

            annual = AnnualSubjectResult.objects.filter(
                student=student, school=school, academic_year=year
            )

            att = StudentAttendance.objects.filter(
                student=student,
                session__school=school,
                session__date__gte=since,
            )

            children.append(
                {
                    "link": link,
                    "student": student,
                    "enrollment": enrollment,
                    "total_subj": annual.count(),
                    "passed": annual.filter(status="pass").count(),
                    "failed": annual.filter(status="fail").count(),
                    "incomplete": annual.filter(status="incomplete").count(),
                    "absent_30": att.filter(status="absent").count(),
                    "late_30": att.filter(status="late").count(),
                }
            )

        return children

    @staticmethod
    def get_student_grades(student, school, year=settings.CURRENT_ACADEMIC_YEAR):
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
    def get_student_attendance(student, school, days=30):
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

        by_date = {}
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
