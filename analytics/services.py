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

from django.conf import settings

from datetime import timedelta

from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncMonth
from django.utils import timezone

from assessments.models import (
    AnnualSubjectResult,
    SubjectClassSetup,
)
from core.models import ClassGroup, StudentEnrollment
from operations.models import Session, StudentAttendance


class AnalyticsService:
    # ── اتجاه الحضور اليومي ─────────────────────────────────
    @staticmethod
    def attendance_trend(school, days=30):
        """بيانات اتجاه الحضور خلال فترة محددة"""
        since = timezone.now().date() - timedelta(days=days)

        qs = (
            StudentAttendance.objects.filter(session__school=school, session__date__gte=since)
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
            results.append(
                {
                    "date": row["session__date"],
                    "present_pct": pct,
                    "absent_pct": 100 - pct,
                    "total": row["total"],
                }
            )
        return results

    # ── توزيع الدرجات ───────────────────────────────────────
    @staticmethod
    def grades_distribution(school, year=settings.CURRENT_ACADEMIC_YEAR):
        """توزيع الطلاب على نطاقات الدرجات"""
        results = AnnualSubjectResult.objects.filter(
            school=school,
            academic_year=year,
            annual_total__isnull=False,
        )

        ranges = {
            "90-100": results.filter(annual_total__gte=90).count(),
            "80-89": results.filter(annual_total__gte=80, annual_total__lt=90).count(),
            "70-79": results.filter(annual_total__gte=70, annual_total__lt=80).count(),
            "60-69": results.filter(annual_total__gte=60, annual_total__lt=70).count(),
            "50-59": results.filter(annual_total__gte=50, annual_total__lt=60).count(),
            "< 50": results.filter(annual_total__lt=50).count(),
        }
        return ranges

    # ── مقارنة الفصول ───────────────────────────────────────
    @staticmethod
    def class_comparison(school, year=settings.CURRENT_ACADEMIC_YEAR):
        """مقارنة نسب النجاح بين الفصول"""
        classes = ClassGroup.objects.filter(school=school, academic_year=year, is_active=True)

        data = []
        for cls in classes:
            students = StudentEnrollment.objects.filter(
                class_group=cls, is_active=True
            ).values_list("student_id", flat=True)

            total = AnnualSubjectResult.objects.filter(
                student_id__in=students,
                school=school,
                academic_year=year,
            ).count()
            passed = AnnualSubjectResult.objects.filter(
                student_id__in=students,
                school=school,
                academic_year=year,
                status="pass",
            ).count()

            pct = round(passed / total * 100) if total else 0
            data.append(
                {
                    "class_name": f"{cls.get_grade_display()} / {cls.section}",
                    "pass_pct": pct,
                    "total": total,
                    "passed": passed,
                }
            )

        return data

    # ── مقارنة المواد ───────────────────────────────────────
    @staticmethod
    def subject_comparison(school, year=settings.CURRENT_ACADEMIC_YEAR):
        """مقارنة متوسط الدرجات بين المواد"""
        setups = (
            SubjectClassSetup.objects.filter(school=school, academic_year=year, is_active=True)
            .select_related("subject")
            .values("subject__name_ar")
            .annotate(
                avg_score=Avg(
                    "annualresults__annual_total",
                    filter=Q(annualresults__annual_total__isnull=False),
                ),
                pass_count=Count("annualresults", filter=Q(annualresults__status="pass")),
                total_count=Count("annualresults"),
            )
        )

        data = []
        for row in setups:
            data.append(
                {
                    "subject": row["subject__name_ar"],
                    "avg": round(float(row["avg_score"]), 1) if row["avg_score"] else 0,
                    "pass_pct": round(row["pass_count"] / row["total_count"] * 100)
                    if row["total_count"]
                    else 0,
                }
            )
        return sorted(data, key=lambda x: x["avg"], reverse=True)

    # ── الراسبون حسب الفصل ──────────────────────────────────
    @staticmethod
    def failing_by_class(school, year=settings.CURRENT_ACADEMIC_YEAR):
        """عدد الراسبين في كل فصل"""
        classes = ClassGroup.objects.filter(school=school, academic_year=year, is_active=True)

        data = []
        for cls in classes:
            students = StudentEnrollment.objects.filter(
                class_group=cls, is_active=True
            ).values_list("student_id", flat=True)

            fail_count = (
                AnnualSubjectResult.objects.filter(
                    student_id__in=students,
                    school=school,
                    academic_year=year,
                    status="fail",
                )
                .values("student")
                .distinct()
                .count()
            )

            data.append(
                {
                    "class_name": f"{cls.get_grade_display()} / {cls.section}",
                    "fail_count": fail_count,
                    "total": len(students),
                }
            )
        return data

    # ── اتجاه السلوك ───────────────────────────────────────
    @staticmethod
    def behavior_trend(school, months=6):
        """اتجاه المخالفات السلوكية شهرياً"""
        from behavior.models import BehaviorInfraction

        since = timezone.now().date() - timedelta(days=months * 30)
        qs = (
            BehaviorInfraction.objects.filter(school=school, date__gte=since)
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
            ClinicVisit.objects.filter(school=school, created_at__date__gte=since)
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
    def plan_progress(school, year=settings.CURRENT_ACADEMIC_YEAR):
        """تقدم الخطة التشغيلية حسب المجال"""
        from quality.services import QualityService

        return QualityService.get_progress_report_data(school, year)


# ══════════════════════════════════════════════════════════════════════
# KPIService — حساب المؤشرات العشرة + إنشاء تقرير PDF
# ══════════════════════════════════════════════════════════════════════


class KPIService:
    """
    يحسب المؤشرات الكمية العشرة لمدرسة وشهر محدد.
    مستقل عن HTTP — يمكن استدعاؤه من view أو Celery task.
    """

    @staticmethod
    def compute(school, year: str = settings.CURRENT_ACADEMIC_YEAR) -> dict:
        """
        يعيد dict يحتوي على:
          - kpis        : قاموس المؤشرات العشرة مع traffic light
          - summary     : إحصاء (green/yellow/red/grey)
          - school, year, generated_at, month_label
        """
        from django.utils import timezone

        from behavior.models import BehaviorInfraction
        from core.models import BookBorrowing, Membership, StudentEnrollment
        from operations.models import StudentAttendance, TeacherAbsence

        today = timezone.now().date()
        month = today.month
        kpis = {}

        # ── 1: نسبة حضور الطلبة ──────────────────────────────────────
        sessions_m = Session.objects.filter(school=school, date__month=month, date__year=today.year)
        att_all = StudentAttendance.objects.filter(session__in=sessions_m)
        present = att_all.filter(status="present").count()
        total_att = att_all.count()
        kpis["student_attendance_pct"] = {
            "label": "نسبة حضور الطلبة",
            "unit": "%",
            "frequency": "أسبوعي",
            "value": round(present / total_att * 100, 1) if total_att else 0,
            "target": 95,
            "warning": 90,
            "direction": "higher_better",
        }

        # ── 2: مخالفات / 100 طالب ────────────────────────────────────
        total_students = StudentEnrollment.objects.filter(
            class_group__school=school,
            class_group__academic_year=year,
            is_active=True,
        ).count()
        infractions_m = BehaviorInfraction.objects.filter(
            school=school, date__month=month, date__year=today.year
        ).count()
        kpis["infractions_per_100"] = {
            "label": "مخالفات / 100 طالب",
            "unit": "",
            "frequency": "شهري",
            "value": round(infractions_m / total_students * 100, 2) if total_students else 0,
            "target": 3,
            "warning": 5,
            "direction": "lower_better",
        }

        # ── 3: رصد الدرجات في الوقت ──────────────────────────────────
        try:
            from exam_control.models import ExamGradeSheet

            total_sheets = ExamGradeSheet.objects.filter(schedule__session__school=school).count()
            submitted = ExamGradeSheet.objects.filter(
                schedule__session__school=school, status="submitted"
            ).count()
            grading_pct = round(submitted / total_sheets * 100, 1) if total_sheets else 100
        except Exception:
            grading_pct = 100
        kpis["grading_on_time_pct"] = {
            "label": "رصد الدرجات في الوقت",
            "unit": "%",
            "frequency": "فصلي",
            "value": grading_pct,
            "target": 98,
            "warning": 95,
            "direction": "higher_better",
        }

        # ── 4: أيام اختبار بلا حوادث ─────────────────────────────────
        try:
            from exam_control.models import ExamIncident, ExamSession

            exam_days = set(
                ExamSession.objects.filter(school=school).values_list("start_date", flat=True)
            )
            incident_days = set(
                ExamIncident.objects.filter(session__school=school, severity__gte=2).values_list(
                    "incident_time__date", flat=True
                )
            )
            clean_pct = (
                round(len(exam_days - incident_days) / len(exam_days) * 100, 1)
                if exam_days
                else 100
            )
        except Exception:
            clean_pct = 100
        kpis["exam_clean_days_pct"] = {
            "label": "أيام اختبار بلا حوادث",
            "unit": "%",
            "frequency": "فصلي",
            "value": clean_pct,
            "target": 100,
            "warning": 99,
            "direction": "higher_better",
        }

        # ── 5: غياب المعلمين غير المبرر ──────────────────────────────
        teacher_days = (
            Membership.objects.filter(
                school=school,
                is_active=True,
                role__name__in=["teacher", "coordinator"],
            ).count()
            * 20
        )
        unexcused = TeacherAbsence.objects.filter(
            school=school,
            date__month=month,
            date__year=today.year,
            is_excused=False,
        ).count()
        kpis["teacher_unexcused_abs_pct"] = {
            "label": "غياب المعلمين غير المبرر",
            "unit": "%",
            "frequency": "شهري",
            "value": round(unexcused / teacher_days * 100, 2) if teacher_days else 0,
            "target": 1,
            "warning": 2,
            "direction": "lower_better",
        }

        # ── 6: حوادث النقل / 100,000 كم ──────────────────────────────
        kpis["transport_incidents_rate"] = {
            "label": "حوادث النقل / 100,000 كم",
            "unit": "",
            "frequency": "شهري",
            "value": 0,
            "target": 0,
            "warning": 0.1,
            "direction": "lower_better",
            "note": "يُحدَّث عند ربط GPS",
        }

        # ── 7: استعارة المكتبة / طالب ────────────────────────────────
        borrows = BookBorrowing.objects.filter(
            book__school=school, borrow_date__year=today.year
        ).count()
        kpis["library_borrows_per_student"] = {
            "label": "استعارة المكتبة / طالب",
            "unit": "",
            "frequency": "فصلي",
            "value": round(borrows / total_students, 2) if total_students else 0,
            "target": 2,
            "warning": 1,
            "direction": "higher_better",
        }

        # ── 8-10: مؤشرات يدوية ───────────────────────────────────────
        kpis["canteen_health_compliance_pct"] = {
            "label": "مطابقة المقصف للصحة",
            "unit": "%",
            "frequency": "فصلي",
            "value": None,
            "target": 95,
            "warning": 90,
            "direction": "higher_better",
            "note": "يُدخَل يدوياً من تقارير وزارة الصحة",
        }
        kpis["evacuation_plan_pct"] = {
            "label": "تنفيذ خطط الإخلاء",
            "unit": "%",
            "frequency": "فصلي",
            "value": None,
            "target": 100,
            "warning": 99,
            "direction": "higher_better",
            "note": "يُسجَّل بعد كل تدريب إخلاء",
        }
        kpis["professional_dev_hours"] = {
            "label": "ساعات التطوير المهني / معلم",
            "unit": "ساعة",
            "frequency": "فصلي",
            "value": None,
            "target": 10,
            "warning": 6,
            "direction": "higher_better",
            "note": "يُسجَّل من محاضر ورش التطوير",
        }

        # ── ضوء المرور ────────────────────────────────────────────────
        for kpi in kpis.values():
            val = kpi.get("value")
            if val is None:
                kpi["traffic"] = "grey"
            else:
                d = kpi.get("direction", "higher_better")
                t, w = kpi["target"], kpi["warning"]
                if d == "higher_better":
                    kpi["traffic"] = "green" if val >= t else ("yellow" if val >= w else "red")
                else:
                    kpi["traffic"] = "green" if val <= t else ("yellow" if val <= w else "red")

        summary = {"green": 0, "yellow": 0, "red": 0, "grey": 0}
        for kpi in kpis.values():
            summary[kpi["traffic"]] += 1

        return {
            "kpis": kpis,
            "summary": summary,
            "school": school,
            "year": year,
            "generated_at": today,
            "month_label": today.strftime("%B %Y"),
        }
