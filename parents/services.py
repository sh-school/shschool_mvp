"""
parents/services.py
━━━━━━━━━━━━━━━━━━
Business logic لبوابة ولي الأمر
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.db.models import Count, Q
from django.utils import timezone

from assessments.models import AnnualSubjectResult, StudentSubjectResult
from core.academic_calendar import academic_year_for_school
from core.domain.attendance import attendance_rate
from core.domain.tones import ATTENDANCE_KPI, GRADE_CELL, tone_for
from core.models import ParentStudentLink, StudentEnrollment
from operations.models import StudentAttendance

if TYPE_CHECKING:
    from core.models import CustomUser, School


class ParentService:
    @staticmethod
    def get_children_data(
        user: CustomUser,
        school: School,
        year: str | None = None,
    ) -> list:
        """
        يعيد قائمة بأبناء ولي الأمر مع إحصائيات كل طالب.
        كل عنصر: {link, student, enrollment, total_subj, passed,
                   failed, incomplete, absent_30, late_30}
        """
        year = year or academic_year_for_school(school)
        links = (
            ParentStudentLink.objects.filter(parent=user, school=school)
            .select_related("student")
            .order_by("student__full_name")
        )
        since = timezone.now().date() - timedelta(days=30)

        student_ids = [link.student_id for link in links]

        # Bulk: enrollments keyed by student_id
        enrollments_map: dict = {}
        for enr in StudentEnrollment.objects.filter(
            student_id__in=student_ids, is_active=True
        ).select_related("class_group"):
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
        year: str | None = None,
    ) -> dict:
        """ملخص الدرجات لطالب"""
        year = year or academic_year_for_school(school)
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
                "tone": _grade_tone(ann.annual_total),
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
    def get_student_attendance(student: CustomUser, school: School, days: int = 30) -> dict:
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
        for day in by_date.values():
            day["sessions_label"] = f"{len(day['records'])} حصص"

        total = attendance.count()
        absent = attendance.filter(status="absent").count()
        late = attendance.filter(status="late").count()
        present = attendance.filter(status="present").count()

        today = timezone.now().date()
        return {
            "days_list": sorted(by_date.values(), key=lambda x: x["date"], reverse=True),
            "weeks": attendance_weeks(by_date, since, today),
            "flagged_days": [
                day
                for day in sorted(by_date.values(), key=lambda x: x["date"], reverse=True)
                if day["has_absent"] or day["has_late"]
            ],
            "total": total,
            "present": present,
            "absent": absent,
            "late": late,
            "att_pct": attendance_rate(present, total),
            "since": since,
        }

    @staticmethod
    def enrich_children_dashboard(children: list, school: School, today=None) -> list:
        """
        يُثري بيانات الأبناء بـ 4 batch queries بدل N+1.

        ✅ v5.4: ينقل batch enrichment من parent_dashboard view إلى service layer.

        Args:
            children: القائمة المُعادة من get_children_data()
            school: كائن المدرسة
            today: تاريخ اليوم (افتراضي: اليوم الفعلي)

        Returns:
            children مع إضافة: behavior_score, subjects_count,
                                attendance_pct, week_attendance لكل طالب
        """
        from collections import defaultdict

        today = today or timezone.now().date()
        student_ids = [cd["student"].pk for cd in children if cd.get("student")]

        if not student_ids:
            return children

        # نظام النقاط ملغى — لا deducted/recovered maps

        # Batch: نسبة الحضور خلال 30 يومًا لكل طالب
        att_stats: dict = {}
        for row in (
            StudentAttendance.objects.filter(
                student_id__in=student_ids,
                session__school=school,
                session__date__gte=today - timedelta(days=30),
            )
            .values("student_id")
            .annotate(
                total=Count("id"),
                present=Count("id", filter=Q(status="present")),
            )
        ):
            att_stats[row["student_id"]] = row

        # (4) Batch: اتجاه الحضور آخر 7 أيام لكل طالب
        week_att_map: dict = defaultdict(list)
        for row in (
            StudentAttendance.objects.filter(
                student_id__in=student_ids,
                session__school=school,
                session__date__gte=today - timedelta(days=7),
            )
            .values("student_id", "session__date")
            .annotate(
                present=Count("id", filter=Q(status="present")),
                absent=Count("id", filter=Q(status="absent")),
            )
            .order_by("student_id", "session__date")
        ):
            week_att_map[row["student_id"]].append(row)

        for child_data in children:
            student = child_data.get("student")
            if not student:
                continue
            sid = student.pk
            child_data["subjects_count"] = child_data.get("total_subj", 0)

            att = att_stats.get(sid, {})
            att_total = att.get("total", 0)
            att_present = att.get("present", 0)
            child_data["attendance_pct"] = attendance_rate(att_present, att_total, empty=None)
            child_data["week_attendance"] = week_att_map.get(sid, [])
            child_data["kpis"] = _child_kpis(child_data)

        return children


def _child_kpis(child: dict) -> list[dict]:
    """أرقامُ بطاقة الابن جاهزةً للوسم `{% kpi %}` — والحكمُ في اللون يُكتب هنا.

    كان القالبُ يزن كلَّ رقمٍ بشرطٍ ويكرّر حكمَه ثلاثاً: لونٌ، وسطرُ تنبيهٍ تحت
    الرقم، وشريطُ تنبيهٍ تحت البطاقات. فاللونُ وحدَه يحمل الحكم هنا، والعتباتُ
    هي التي كانت: الحضورُ 90 فأعلى أخضر و75 فأعلى كهرمانيّ، والغيابُ خمسةٌ فأكثر
    أحمر، والرسوبُ في مادّةٍ أحمر.

    و«درجةُ السلوك» حُذفت: نظامُ النقاط ملغى، ولا يحسبها أحد — فكانت تُعرض 100
    خضراءَ لكلّ ابنٍ مهما كان سلوكُه. رقمٌ لا يُقاس لا يُعرض.
    """
    link = child["link"]
    kpis = []
    if link.can_view_attendance:
        pct = child.get("attendance_pct")
        kpis.append(
            {
                "label": "الحضور",
                "value": "—" if pct is None else f"{pct}%",
                "sub": "30 يوماً",
                "tone": tone_for(pct, ATTENDANCE_KPI, empty="blue"),
                "title": "نسبةُ الحصص الحاضرة في آخر 30 يوماً",
            }
        )
        absent, late = child.get("absent_30") or 0, child.get("late_30") or 0
        kpis.append(
            {
                "label": "الغياب",
                "value": absent,
                "sub": f"و{late} تأخّر" if late else "",
                "tone": tone_for(absent, ABSENCE_DAYS_KPI),
                "title": "أيّامُ الغياب في آخر 30 يوماً",
            }
        )
    if link.can_view_grades:
        failed, passed = child.get("failed") or 0, child.get("passed") or 0
        kpis.append(
            {
                "label": "المواد",
                "value": child.get("subjects_count") or 0,
                "sub": f"راسب في {failed}" if failed else "",
                "tone": "red" if failed else "blue",
                "title": f"ناجح {passed} · راسب {failed}",
            }
        )
    return kpis


#: أيّامُ الغياب في بطاقة الابن: خمسةٌ فأكثر أحمر، ويومٌ واحدٌ كهرمانيّ، ولا شيءَ أخضر.
ABSENCE_DAYS_KPI = ((5, "red"), (1, "amber"), (None, "green"))

#: أيّامُ الدراسة بترتيب الأسبوع القطريّ: الأحد (6 في بايثون) إلى الخميس (3).
SCHOOL_WEEKDAYS = (6, 0, 1, 2, 3)


def attendance_weeks(by_date: dict, since, today) -> list[list[dict]]:
    """تقويمُ الفترة أسابيعَ من خمسة أيّام — خانةٌ لكلّ يومِ دراسة.

    كانت الصفحةُ بطاقةً لكلّ يوم: ستّون يوماً تعني أربعين بطاقةً متراصّةً على
    هاتف. والتقويمُ يضع الفترةَ كلَّها في شاشةٍ واحدة، واللونُ يقول الحال:
    ``absent`` غياب، و``late`` تأخّر، و``present`` منتظم، و``none`` يومٌ بلا
    حصصٍ مرصودة، و``future``/``before`` خارج الفترة (يُرسمان فراغاً).
    """
    start = since - timedelta(days=(since.weekday() - 6) % 7)  # أحدُ أسبوع البداية
    weeks, cursor = [], start
    while cursor <= today:
        week = []
        for offset in range(5):
            day = cursor + timedelta(days=offset)
            record = by_date.get(day)
            if day < since:
                state = "before"
            elif day > today:
                state = "future"
            elif record is None:
                state = "none"
            elif record["has_absent"]:
                state = "absent"
            elif record["has_late"]:
                state = "late"
            else:
                state = "present"
            week.append({"date": day, "state": state})
        if any(cell["state"] not in ("before", "future") for cell in week):
            weeks.append(week)
        cursor += timedelta(days=7)
    # الشهرُ يُكتب حيث يبدأ — في أوّل خانةٍ ظاهرة وفي أوّل كلّ شهر — وإلّا
    # قُرئت «30، 31، 1» تسلسلاً بلا فاصلٍ بين أغسطس وسبتمبر.
    first = True
    for week in weeks:
        for cell in week:
            if cell["state"] in ("before", "future"):
                continue
            day = cell["date"]
            cell["label"] = f"{day.day}/{day.month}" if first or day.day == 1 else str(day.day)
            first = False
    return weeks


def _grade_tone(total) -> str:
    """لونُ المجموع السنويّ — سُلَّمُ خانة الدرجة الواحد: 80 · 65 · 50."""
    return tone_for(total, GRADE_CELL)
