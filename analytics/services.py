"""
analytics/services.py
━━━━━━━━━━━━━━━━━━━━
Business logic لوحدة التحليلات

يشمل:
  - تجميع بيانات الحضور الزمنية
  - توزيع الدرجات
  - مقارنة الفصول والمواد
  - إحصائيات السلوك والعيادة
  - KPIs العشرة
"""
from datetime import timedelta
from django.db.models import Count, Avg, Sum, Q, F
from django.db.models.functions import TruncMonth
from django.utils import timezone

from operations.models import StudentAttendance, Session
from assessments.models import (
    AnnualSubjectResult, StudentSubjectResult,
    SubjectClassSetup, AssessmentPackage,
)
from core.models import ClassGroup, StudentEnrollment, School


class AnalyticsService:

    # ── اتجاه الحضور اليومي ─────────────────────────────────
    @staticmethod
    def attendance_trend(school, days=30):
        """بيانات اتجاه الحضور خلال فترة محددة"""
        since = timezone.now().date() - timedelta(days=days)

        qs = (
            StudentAttendance.objects
            .filter(session__school=school, session__date__gte=since)
            .values("session__date")
            .annotate(
                total=Count("id"),
                present=Count("id", filter=Q(status="present")),
            )
            .order_by("session__date")
        )

        results = []
        for row in qs:
            pct = round(row["present"] / row["total"] * 100) if row["total"] else 0
            results.append({
                "date":        row["session__date"],
                "present_pct": pct,
                "absent_pct":  100 - pct,
                "total":       row["total"],
            })
        return results

    # ── توزيع الدرجات ───────────────────────────────────────
    @staticmethod
    def grades_distribution(school, year="2025-2026"):
        """توزيع الطلاب على نطاقات الدرجات"""
        results = AnnualSubjectResult.objects.filter(
            school=school, academic_year=year,
            annual_total__isnull=False,
        )

        ranges = {
            "90-100": results.filter(annual_total__gte=90).count(),
            "80-89":  results.filter(annual_total__gte=80, annual_total__lt=90).count(),
            "70-79":  results.filter(annual_total__gte=70, annual_total__lt=80).count(),
            "60-69":  results.filter(annual_total__gte=60, annual_total__lt=70).count(),
            "50-59":  results.filter(annual_total__gte=50, annual_total__lt=60).count(),
            "< 50":   results.filter(annual_total__lt=50).count(),
        }
        return ranges

    # ── مقارنة الفصول ───────────────────────────────────────
    @staticmethod
    def class_comparison(school, year="2025-2026"):
        """مقارنة نسب النجاح بين الفصول"""
        classes = ClassGroup.objects.filter(
            school=school, academic_year=year, is_active=True
        )

        data = []
        for cls in classes:
            students = StudentEnrollment.objects.filter(
                class_group=cls, is_active=True
            ).values_list("student_id", flat=True)

            total = AnnualSubjectResult.objects.filter(
                student_id__in=students, school=school, academic_year=year,
            ).count()
            passed = AnnualSubjectResult.objects.filter(
                student_id__in=students, school=school, academic_year=year,
                status="pass",
            ).count()

            pct = round(passed / total * 100) if total else 0
            data.append({
                "class_name": f"{cls.get_grade_display()} / {cls.section}",
                "pass_pct":   pct,
                "total":      total,
                "passed":     passed,
            })

        return data

    # ── مقارنة المواد ───────────────────────────────────────
    @staticmethod
    def subject_comparison(school, year="2025-2026"):
        """مقارنة متوسط الدرجات بين المواد"""
        setups = (
            SubjectClassSetup.objects.filter(
                school=school, academic_year=year, is_active=True
            )
            .select_related("subject")
            .values("subject__name_ar")
            .annotate(
                avg_score=Avg("annualresults__annual_total",
                              filter=Q(annualresults__annual_total__isnull=False)),
                pass_count=Count("annualresults",
                                 filter=Q(annualresults__status="pass")),
                total_count=Count("annualresults"),
            )
        )

        data = []
        for row in setups:
            data.append({
                "subject":  row["subject__name_ar"],
                "avg":      round(float(row["avg_score"]), 1) if row["avg_score"] else 0,
                "pass_pct": round(row["pass_count"] / row["total_count"] * 100) if row["total_count"] else 0,
            })
        return sorted(data, key=lambda x: x["avg"], reverse=True)

    # ── الراسبون حسب الفصل ──────────────────────────────────
    @staticmethod
    def failing_by_class(school, year="2025-2026"):
        """عدد الراسبين في كل فصل"""
        classes = ClassGroup.objects.filter(
            school=school, academic_year=year, is_active=True
        )

        data = []
        for cls in classes:
            students = StudentEnrollment.objects.filter(
                class_group=cls, is_active=True
            ).values_list("student_id", flat=True)

            fail_count = AnnualSubjectResult.objects.filter(
                student_id__in=students, school=school,
                academic_year=year, status="fail",
            ).values("student").distinct().count()

            data.append({
                "class_name":  f"{cls.get_grade_display()} / {cls.section}",
                "fail_count":  fail_count,
                "total":       len(students),
            })
        return data

    # ── اتجاه السلوك ───────────────────────────────────────
    @staticmethod
    def behavior_trend(school, months=6):
        """اتجاه المخالفات السلوكية شهرياً"""
        from behavior.models import BehaviorInfraction

        since = timezone.now().date() - timedelta(days=months * 30)
        qs = (
            BehaviorInfraction.objects
            .filter(school=school, date__gte=since)
            .annotate(month=TruncMonth("date"))
            .values("month")
            .annotate(
                total=Count("id"),
                level1=Count("id", filter=Q(level=1)),
                level2=Count("id", filter=Q(level=2)),
                level3=Count("id", filter=Q(level=3)),
                level4=Count("id", filter=Q(level=4)),
            )
            .order_by("month")
        )
        return list(qs)

    # ── إحصائيات العيادة ────────────────────────────────────
    @staticmethod
    def clinic_stats(school, months=6):
        """إحصائيات زيارات العيادة"""
        from clinic.models import ClinicVisit

        since = timezone.now().date() - timedelta(days=months * 30)
        qs = (
            ClinicVisit.objects
            .filter(school=school, created_at__date__gte=since)
            .annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(
                total=Count("id"),
                sent_home=Count("id", filter=Q(is_sent_home=True)),
            )
            .order_by("month")
        )
        return list(qs)

    # ── تقدم الخطة التشغيلية ────────────────────────────────
    @staticmethod
    def plan_progress(school, year="2025-2026"):
        """تقدم الخطة التشغيلية حسب المجال"""
        from quality.services import QualityService
        return QualityService.get_progress_report_data(school, year)
