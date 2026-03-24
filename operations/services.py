from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import transaction
from django.db.models import Count, QuerySet

from core.models import StudentEnrollment
from operations.models import (
    AbsenceAlert,
    ScheduleSlot,
    Session,
    StudentAttendance,
    SubstituteAssignment,
    TeacherAbsence,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.models import ClassGroup, CustomUser, School


class AttendanceService:
    @staticmethod
    @transaction.atomic
    def mark_attendance(
        session: Session,
        student: CustomUser,
        status: str,
        excuse_type: str = "",
        excuse_notes: str = "",
        marked_by: CustomUser | None = None,
    ) -> tuple:
        att, created = StudentAttendance.objects.update_or_create(
            session=session,
            student=student,
            defaults={
                "school": session.school,
                "status": status,
                "excuse_type": excuse_type,
                "excuse_notes": excuse_notes,
                "marked_by": marked_by,
            },
        )
        # Check absence threshold
        if status == "absent":
            AttendanceService.check_absence_threshold(student, session.school)
        return att, created

    @staticmethod
    @transaction.atomic
    def bulk_mark_all_present(
        session: Session, marked_by: CustomUser | None = None
    ) -> int:
        students = StudentEnrollment.objects.filter(
            class_group=session.class_group, is_active=True
        ).select_related("student")

        records = []
        for enrollment in students:
            records.append(
                StudentAttendance(
                    session=session,
                    student=enrollment.student,
                    school=session.school,
                    status="present",
                    marked_by=marked_by,
                )
            )
        StudentAttendance.objects.bulk_create(records, ignore_conflicts=True)
        session.status = "in_progress"
        session.save(update_fields=["status"])
        return len(records)

    @staticmethod
    @transaction.atomic
    def complete_session(session: Session) -> None:
        session.status = "completed"
        session.save(update_fields=["status"])

    # ── إعداد السنة الدراسية (المادة 7 من قانون 25/2001 المعدّل) ─
    SCHOOL_YEAR_DAYS = 190  # أيام الدراسة الرسمية سنوياً
    ABSENCE_THRESHOLD_PCT = 0.10  # 10% = الحد القانوني للغياب

    @staticmethod
    def check_absence_threshold(student: CustomUser, school: School) -> None:
        """
        المادة 7 — قانون التعليم الإلزامي 25/2001:
        العتبة القانونية: تجاوز 10% من أيام الدراسة (≈19 يوماً من 190).
        تُخطر المدرسة ولي الأمر، وإذا عاود الغياب تُخطر الوزارة خلال أسبوع.
        """
        school_year = settings.CURRENT_ACADEMIC_YEAR
        year_start = date(2025, 9, 1)
        year_end = date(2026, 6, 30)

        # إجمالي الحصص المسجَّلة للطالب في هذه السنة
        total_sessions = StudentAttendance.objects.filter(
            student=student,
            school=school,
            session__date__gte=year_start,
            session__date__lte=year_end,
        ).count()

        # إجمالي الغياب بدون عذر
        unexcused_absent = StudentAttendance.objects.filter(
            student=student,
            school=school,
            status="absent",
            excuse_type="",
            session__date__gte=year_start,
            session__date__lte=year_end,
        ).count()

        # حساب النسبة المئوية الفعلية
        base = total_sessions if total_sessions > 0 else AttendanceService.SCHOOL_YEAR_DAYS
        threshold_days = int(base * AttendanceService.ABSENCE_THRESHOLD_PCT)

        if unexcused_absent >= threshold_days:
            alert, created = AbsenceAlert.objects.get_or_create(
                school=school,
                student=student,
                status="pending",
                period_start=year_start,
                period_end=year_end,
                defaults={"absence_count": unexcused_absent},
            )
            # إرسال إشعار للأولياء عند إنشاء التنبيه لأول مرة
            if created:
                try:
                    from notifications.hub import NotificationHub

                    NotificationHub.dispatch_to_parents(
                        event_type="absence",
                        school=school,
                        student=student,
                        title=f"⚠️ تنبيه غياب — {student.full_name}",
                        body=(
                            f"تجاوز ابنكم العتبة القانونية للغياب بدون عذر "
                            f"({unexcused_absent} يوماً من أصل {threshold_days} مسموح).\n"
                            f"يُرجى التواصل مع المدرسة."
                        ),
                        context={"student": student, "absence_count": unexcused_absent},
                        related_url=f"/operations/attendance/student/{student.pk}/",
                    )
                except (ImportError, OSError, RuntimeError, ValueError) as exc:
                    logger.warning(
                        "check_absence_threshold: Hub dispatch failed [student=%s]: %s",
                        student.pk,
                        exc,
                    )

    @staticmethod
    def get_session_summary(session: Session) -> dict:
        att = StudentAttendance.objects.filter(session=session)
        total = att.count()
        present = att.filter(status="present").count()
        absent = att.filter(status="absent").count()
        late = att.filter(status="late").count()
        excused = att.filter(status="excused").count()
        pct = round(present / total * 100) if total else 0
        return {
            "total": total,
            "present": present,
            "absent": absent,
            "late": late,
            "excused": excused,
            "percentage": pct,
        }


# ─────────────────────────────────────────────
# المرحلة 2 — الجداول الذكية + نظام البديل
# ─────────────────────────────────────────────


class ScheduleService:
    # ── الجدول الأسبوعي ──────────────────────

    @staticmethod
    def get_weekly_schedule(
        school: School,
        teacher: CustomUser | None = None,
        class_group: ClassGroup | None = None,
        academic_year: str = settings.CURRENT_ACADEMIC_YEAR,
    ) -> dict:
        """إرجاع الجدول الأسبوعي مرتّباً حسب اليوم والحصة"""
        qs = ScheduleSlot.objects.filter(
            school=school, academic_year=academic_year, is_active=True
        ).select_related("teacher", "class_group", "subject")
        if teacher:
            qs = qs.filter(teacher=teacher)
        if class_group:
            qs = qs.filter(class_group=class_group)

        # بناء matrix: {يوم: {رقم_حصة: slot}}
        grid: dict = {d: {} for d in range(5)}  # 0=أحد … 4=خميس
        for slot in qs:
            grid[slot.day_of_week][slot.period_number] = slot
        return grid

    @staticmethod
    def detect_conflicts(
        school: School, academic_year: str = settings.CURRENT_ACADEMIC_YEAR
    ) -> list:
        """كشف التعارضات في الجدول"""
        conflicts: list = []

        # تعارض المعلم: نفس المعلم في نفس اليوم والحصة
        teacher_dups = (
            ScheduleSlot.objects.filter(school=school, academic_year=academic_year, is_active=True)
            .values("teacher", "day_of_week", "period_number")
            .annotate(cnt=Count("id"))
            .filter(cnt__gt=1)
        )
        for dup in teacher_dups:
            slots = ScheduleSlot.objects.filter(
                school=school,
                teacher_id=dup["teacher"],
                day_of_week=dup["day_of_week"],
                period_number=dup["period_number"],
                is_active=True,
            ).select_related("teacher", "class_group")
            conflicts.append(
                {
                    "type": "teacher",
                    "message": f"تعارض معلم: {slots[0].teacher.full_name} — {slots[0].day_name} ح{dup['period_number']}",
                    "slots": list(slots),
                }
            )

        # تعارض الفصل: نفس الفصل في نفس اليوم والحصة
        class_dups = (
            ScheduleSlot.objects.filter(school=school, academic_year=academic_year, is_active=True)
            .values("class_group", "day_of_week", "period_number")
            .annotate(cnt=Count("id"))
            .filter(cnt__gt=1)
        )
        for dup in class_dups:
            slots = ScheduleSlot.objects.filter(
                school=school,
                class_group_id=dup["class_group"],
                day_of_week=dup["day_of_week"],
                period_number=dup["period_number"],
                is_active=True,
            ).select_related("teacher", "class_group")
            conflicts.append(
                {
                    "type": "class",
                    "message": f"تعارض فصل: {slots[0].class_group} — {slots[0].day_name} ح{dup['period_number']}",
                    "slots": list(slots),
                }
            )

        return conflicts

    @staticmethod
    @transaction.atomic
    def generate_daily_sessions(
        school: School,
        date: date,
        academic_year: str = settings.CURRENT_ACADEMIC_YEAR,
    ) -> int:
        """توليد Session يومية من ScheduleSlot للتاريخ المحدد"""
        day_of_week = date.weekday()  # Python: 0=Mon … لكننا نريد 0=Sun
        # تحويل: Sun=6 في Python → 0 عندنا
        mapping = {6: 0, 0: 1, 1: 2, 2: 3, 3: 4}
        our_day = mapping.get(day_of_week, -1)
        if our_day == -1:
            return 0  # جمعة أو سبت

        slots = ScheduleSlot.objects.filter(
            school=school, day_of_week=our_day, academic_year=academic_year, is_active=True
        ).select_related("teacher", "class_group", "subject")

        created = 0
        for slot in slots:
            _, was_created = Session.objects.get_or_create(
                school=school,
                teacher=slot.teacher,
                class_group=slot.class_group,
                date=date,
                start_time=slot.start_time,
                defaults={
                    "subject": slot.subject,
                    "end_time": slot.end_time,
                    "status": "scheduled",
                },
            )
            if was_created:
                created += 1
        return created


class SubstituteService:
    @staticmethod
    def get_available_teachers(
        school: School,
        date: date,
        day_of_week: int,
        period_number: int,
        exclude_teacher: CustomUser | None = None,
    ) -> QuerySet:
        """
        إيجاد معلمين متاحين للبدل:
        - لديهم membership نشطة في المدرسة
        - ليس لديهم حصة في نفس اليوم والحصة
        - لم يُسجَّل غيابهم في نفس اليوم
        """
        from core.models import Membership

        # جميع معلمي المدرسة
        teacher_ids = Membership.objects.filter(
            school=school, is_active=True, role__name__in=("teacher", "coordinator")
        ).values_list("user_id", flat=True)

        if exclude_teacher:
            teacher_ids = [t for t in teacher_ids if t != exclude_teacher.id]

        # من لديهم حصة في نفس الوقت
        busy_ids = ScheduleSlot.objects.filter(
            school=school, day_of_week=day_of_week, period_number=period_number, is_active=True
        ).values_list("teacher_id", flat=True)

        # من هم غائبون في نفس اليوم
        absent_ids = TeacherAbsence.objects.filter(school=school, date=date).values_list(
            "teacher_id", flat=True
        )

        available_ids = set(teacher_ids) - set(busy_ids) - set(absent_ids)

        from core.models import CustomUser

        return CustomUser.objects.filter(id__in=available_ids).order_by("full_name")

    @staticmethod
    @transaction.atomic
    def register_absence(
        school: School,
        teacher: CustomUser,
        date: date,
        reason: str,
        reason_notes: str = "",
        reported_by: CustomUser | None = None,
    ) -> TeacherAbsence:
        """تسجيل غياب معلم + إنشاء تعيينات البديل تلقائياً"""
        absence, created = TeacherAbsence.objects.get_or_create(
            school=school,
            teacher=teacher,
            date=date,
            defaults={
                "reason": reason,
                "reason_notes": reason_notes,
                "reported_by": reported_by,
                "status": "pending",
            },
        )
        return absence

    @staticmethod
    @transaction.atomic
    def assign_substitute(
        absence: TeacherAbsence,
        slot: ScheduleSlot,
        substitute: CustomUser,
        assigned_by: CustomUser | None = None,
        notes: str = "",
    ) -> SubstituteAssignment:
        """تعيين بديل لحصة محددة"""
        assignment, created = SubstituteAssignment.objects.update_or_create(
            absence=absence,
            slot=slot,
            defaults={
                "substitute": substitute,
                "school": absence.school,
                "assigned_by": assigned_by,
                "notes": notes,
                "status": "assigned",
            },
        )
        # تحديث حالة الغياب
        total_slots = ScheduleSlot.objects.filter(
            school=absence.school,
            teacher=absence.teacher,
            day_of_week=SubstituteService._date_to_day(absence.date),
            is_active=True,
        ).count()
        covered = SubstituteAssignment.objects.filter(
            absence=absence, status__in=("assigned", "confirmed")
        ).count()
        if total_slots > 0 and covered >= total_slots:
            absence.status = "covered"
        else:
            absence.status = "pending"
        absence.save(update_fields=["status"])
        return assignment

    @staticmethod
    def _date_to_day(date: date) -> int:
        mapping = {6: 0, 0: 1, 1: 2, 2: 3, 3: 4}
        return mapping.get(date.weekday(), -1)

    @staticmethod
    def get_substitute_report(
        school: School, date_from: date, date_to: date
    ) -> QuerySet:
        """تقرير الحصص البديلة في فترة"""
        return (
            SubstituteAssignment.objects.filter(
                school=school, absence__date__range=(date_from, date_to)
            )
            .select_related("substitute", "absence__teacher", "slot__class_group", "slot__subject")
            .order_by("absence__date", "slot__period_number")
        )

    @staticmethod
    def suggest_best_substitute(
        school: School,
        target_date: date,
        day_of_week: int,
        period_number: int,
        exclude_teacher: CustomUser | None = None,
    ) -> CustomUser | None:
        """اقتراح أفضل بديل — الأقل حِملاً في البدائل هذا الأسبوع"""
        available = SubstituteService.get_available_teachers(
            school, target_date, day_of_week, period_number, exclude_teacher
        )
        if not available.exists():
            return None

        # حساب عدد بدائل كل معلم هذا الأسبوع
        from datetime import timedelta
        week_start = target_date - timedelta(days=target_date.weekday())
        week_end = week_start + timedelta(days=6)

        sub_counts = {}
        for teacher in available:
            count = SubstituteAssignment.objects.filter(
                substitute=teacher,
                absence__date__range=(week_start, week_end),
                school=school,
            ).count()
            sub_counts[teacher] = count

        # الأقل بدائل هذا الأسبوع
        return min(sub_counts, key=sub_counts.get)
