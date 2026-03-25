from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models, transaction
from django.db.models import Count, QuerySet

from core.models import StudentEnrollment
from operations.models import (
    AbsenceAlert,
    CompensatorySession,
    FreeSlotRegistry,
    ScheduleSlot,
    Session,
    StudentAttendance,
    SubstituteAssignment,
    TeacherAbsence,
    TeacherSwap,
    TimeSlotConfig,
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
    def bulk_mark_all_present(session: Session, marked_by: CustomUser | None = None) -> int:
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
    def get_substitute_report(school: School, date_from: date, date_to: date) -> QuerySet:
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

    @staticmethod
    @transaction.atomic
    def assign_substitute_and_update_session(
        absence: TeacherAbsence,
        slot: ScheduleSlot,
        substitute: "CustomUser",
        assigned_by: "CustomUser | None" = None,
        notes: str = "",
    ) -> SubstituteAssignment:
        """
        تعيين بديل + تحديث Session.teacher (الفجوة الحرجة المكتشفة).
        يضمن أن الحصة اليومية تعكس المعلم الفعلي.
        """
        assignment = SubstituteService.assign_substitute(
            absence, slot, substitute, assigned_by, notes,
        )
        # تحديث Session اليومية إذا وُجدت
        Session.objects.filter(
            school=absence.school,
            teacher=absence.teacher,
            date=absence.date,
            start_time=slot.start_time,
        ).update(teacher=substitute)
        return assignment


# ═════════════════════════════════════════════════════════════════════
# المرحلة 4 — خدمات التبديل والتعويض والحصص الحرة
# ═════════════════════════════════════════════════════════════════════


class FreeSlotService:
    """خدمة سجل الحصص الحرة — يُبنى تلقائياً من فراغات ScheduleSlot."""

    @staticmethod
    @transaction.atomic
    def build_registry(
        school: "School",
        academic_year: str = settings.CURRENT_ACADEMIC_YEAR,
        max_periods: int = 7,
    ) -> int:
        """
        بناء/إعادة بناء سجل الحصص الحرة لكل معلمي المدرسة.
        يمسح القديم ويبني من جديد بناءً على ScheduleSlot.
        """
        from core.models import Membership

        # حذف السجل القديم
        FreeSlotRegistry.objects.filter(school=school, academic_year=academic_year).delete()

        # جميع معلمي المدرسة
        teacher_ids = list(
            Membership.objects.filter(
                school=school, is_active=True,
                role__name__in=("teacher", "coordinator", "ese_teacher"),
            ).values_list("user_id", flat=True)
        )

        # بناء مجموعة الحصص المشغولة لكل معلم
        busy = {}
        slots = ScheduleSlot.objects.filter(
            school=school, academic_year=academic_year, is_active=True,
        ).values_list("teacher_id", "day_of_week", "period_number")

        for tid, day, period in slots:
            busy.setdefault(tid, set()).add((day, period))

        # بناء السجل
        records = []
        for tid in teacher_ids:
            teacher_busy = busy.get(tid, set())
            for day in range(5):  # 0=أحد → 4=خميس
                for period in range(1, max_periods + 1):
                    if (day, period) not in teacher_busy:
                        records.append(FreeSlotRegistry(
                            teacher_id=tid,
                            school=school,
                            day_of_week=day,
                            period_number=period,
                            academic_year=academic_year,
                            is_available=True,
                        ))

        FreeSlotRegistry.objects.bulk_create(records, batch_size=500)
        logger.info("FreeSlotService.build_registry: created %d entries for school %s", len(records), school.code)
        return len(records)

    @staticmethod
    def get_teacher_free_slots(
        teacher: "CustomUser",
        school: "School",
        academic_year: str = settings.CURRENT_ACADEMIC_YEAR,
    ) -> QuerySet:
        """حصص المعلم الفارغة — مرتبة حسب اليوم والحصة."""
        return FreeSlotRegistry.objects.filter(
            teacher=teacher, school=school, academic_year=academic_year, is_available=True,
        ).order_by("day_of_week", "period_number")

    @staticmethod
    def get_free_teachers_at(
        school: "School",
        day_of_week: int,
        period_number: int,
        academic_year: str = settings.CURRENT_ACADEMIC_YEAR,
        department: str = "",
    ) -> QuerySet:
        """
        المعلمون المتاحون في وقت معيّن.
        إذا حُدّد department → يُرشّح حسب القسم.
        """
        from core.models import CustomUser, Membership

        qs = FreeSlotRegistry.objects.filter(
            school=school,
            day_of_week=day_of_week,
            period_number=period_number,
            academic_year=academic_year,
            is_available=True,
        ).values_list("teacher_id", flat=True)

        teachers = CustomUser.objects.filter(id__in=qs).order_by("full_name")

        if department:
            dept_teacher_ids = Membership.objects.filter(
                school=school, is_active=True, department=department,
            ).values_list("user_id", flat=True)
            teachers = teachers.filter(id__in=dept_teacher_ids)

        return teachers


class SwapService:
    """خدمة تبديل الحصص بين المعلمين."""

    # ── ثوابت القوانين ────────────────────────────────────────────
    MIN_ADVANCE_HOURS = 24       # القانون 6: حد أدنى 24 ساعة مسبقاً
    MAX_ADVANCE_DAYS = 14        # القانون 8: حد أقصى 14 يوم مسبقاً
    EXPIRY_HOURS = 48            # القانون 7: انتهاء صلاحية بعد 48 ساعة
    MAX_PENDING_PER_TEACHER = 2  # القانون 8: حد أقصى طلبين معلّقين
    MAX_EXECUTED_PER_MONTH = 4   # القانون 8: حد أقصى 4 تبديلات شهرياً
    # مواد تُعامل كحصص مزدوجة (SC7)
    DOUBLE_PERIOD_SUBJECTS = {"فنون بصرية", "الفنون البصرية", "تكنولوجيا", "التكنولوجيا", "تكنولوجيا المعلومات"}

    # ── التحقق الشامل من قوانين التبديل ───────────────────────────

    @staticmethod
    def validate_swap_request(
        teacher: "CustomUser",
        slot_a: ScheduleSlot,
        slot_b: ScheduleSlot,
        swap_date: date,
        school: "School",
    ) -> list[str]:
        """
        يتحقق من جميع قوانين التبديل — يعيد قائمة أخطاء (فارغة = صالح).

        القوانين:
        1. لا طلب مكرر لنفس الحصة المعلّقة
        2. نفس الفصل فقط
        3. لا تعارض مع طلبات معلّقة على حصة ب
        6. تاريخ مستقبلي + 24 ساعة على الأقل
        7. (تلقائي — cron/management command)
        8a. حد الطلبات المعلّقة (2)
        8b. حد التبديلات الشهرية (4)
        5. حصص مزدوجة تُبدّل كوحدة
        """
        from datetime import datetime, timedelta
        from django.utils import timezone as tz

        errors = []
        now = tz.now()
        today = now.date()

        # ── القانون 2: نفس الفصل ──────────────────────────────────
        if slot_a.class_group_id != slot_b.class_group_id:
            errors.append("التبديل مسموح فقط مع معلمي نفس الفصل")

        # ── القانون 6: تاريخ مستقبلي + 24 ساعة ────────────────────
        if swap_date < today:
            errors.append("لا يمكن التبديل في تاريخ ماضٍ")
        else:
            # حساب 24 ساعة من الآن
            swap_datetime = datetime.combine(swap_date, slot_a.start_time)
            swap_datetime = tz.make_aware(swap_datetime) if tz.is_naive(swap_datetime) else swap_datetime
            if swap_datetime - now < timedelta(hours=SwapService.MIN_ADVANCE_HOURS):
                errors.append("يجب تقديم الطلب قبل 24 ساعة على الأقل من موعد الحصة")

        # ── القانون 6b: حد أقصى 14 يوم ────────────────────────────
        if swap_date > today + timedelta(days=SwapService.MAX_ADVANCE_DAYS):
            errors.append(f"لا يمكن حجز تبديل بعد أكثر من {SwapService.MAX_ADVANCE_DAYS} يوماً")

        # ── القانون 1: لا طلب مكرر لنفس الحصة ─────────────────────
        pending_on_a = TeacherSwap.objects.filter(
            slot_a=slot_a,
            status__in=("pending_b", "accepted_b", "pending_coordinator", "pending_vp"),
        ).exists()
        if pending_on_a:
            errors.append("يوجد طلب تبديل معلّق على هذه الحصة بالفعل")

        # ── القانون 3: لا طلب معلّق على حصة ب ─────────────────────
        pending_on_b = TeacherSwap.objects.filter(
            status__in=("pending_b", "accepted_b", "pending_coordinator", "pending_vp"),
        ).filter(
            models.Q(slot_a=slot_b) | models.Q(slot_b=slot_b)
        ).exists()
        if pending_on_b:
            errors.append("حصة المعلم الآخر عليها طلب تبديل معلّق")

        # ── القانون 8a: حد الطلبات المعلّقة (2) ───────────────────
        pending_count = TeacherSwap.objects.filter(
            teacher_a=teacher,
            status__in=("pending_b", "accepted_b", "pending_coordinator", "pending_vp"),
        ).count()
        if pending_count >= SwapService.MAX_PENDING_PER_TEACHER:
            errors.append(f"لديك {pending_count} طلبات معلّقة — الحد الأقصى {SwapService.MAX_PENDING_PER_TEACHER}")

        # ── القانون 8b: حد التبديلات الشهرية (4) ──────────────────
        month_start = swap_date.replace(day=1)
        next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        executed_this_month = TeacherSwap.objects.filter(
            teacher_a=teacher,
            status="executed",
            swap_date_a__gte=month_start,
            swap_date_a__lt=next_month,
        ).count()
        if executed_this_month >= SwapService.MAX_EXECUTED_PER_MONTH:
            errors.append(f"وصلت للحد الأقصى ({SwapService.MAX_EXECUTED_PER_MONTH} تبديلات) هذا الشهر")

        # ── القانون 5: حصص مزدوجة تُبدّل كوحدة ───────────────────
        subj_name = (slot_a.subject.name_ar if slot_a.subject else "")
        if subj_name in SwapService.DOUBLE_PERIOD_SUBJECTS:
            # ابحث عن الحصة المتتالية لنفس المعلم/الفصل/المادة/اليوم
            adjacent = ScheduleSlot.objects.filter(
                teacher=slot_a.teacher,
                class_group=slot_a.class_group,
                subject=slot_a.subject,
                day_of_week=slot_a.day_of_week,
                is_active=True,
                period_number__in=(slot_a.period_number - 1, slot_a.period_number + 1),
            ).first()
            if adjacent:
                # تأكد أنه لا يوجد استراحة بينهما
                between_min = min(slot_a.period_number, adjacent.period_number)
                between_max = max(slot_a.period_number, adjacent.period_number)
                has_break_between = TimeSlotConfig.objects.filter(
                    school=school,
                    is_break=True,
                    period_number__gt=between_min,
                    period_number__lt=between_max,
                ).exists()
                if not has_break_between:
                    errors.append(
                        f"هذه حصة مزدوجة ({subj_name}) — يجب تبديل الحصتين معاً (ح{adjacent.period_number} أيضاً)"
                    )

        return errors

    @staticmethod
    def get_swap_options(
        teacher: "CustomUser",
        slot: ScheduleSlot,
        school: "School",
    ) -> list:
        """
        معلمي نفس الفصل المتاحين للتبديل مع حصة معيّنة.
        القيد: التبديل مع معلمي نفس الفصل فقط.
        """
        same_class_slots = ScheduleSlot.objects.filter(
            school=school,
            class_group=slot.class_group,
            is_active=True,
        ).exclude(
            teacher=teacher,
        ).select_related("teacher", "class_group", "subject")

        # تصفية: المعلم ب يجب أن يكون فارغاً في وقت الحصة أ
        options = []
        for candidate_slot in same_class_slots:
            # هل المعلم ب فارغ في وقت حصة أ؟
            b_busy_at_a = ScheduleSlot.objects.filter(
                teacher=candidate_slot.teacher,
                day_of_week=slot.day_of_week,
                period_number=slot.period_number,
                is_active=True,
            ).exists()
            # هل المعلم أ فارغ في وقت حصة ب؟
            a_busy_at_b = ScheduleSlot.objects.filter(
                teacher=teacher,
                day_of_week=candidate_slot.day_of_week,
                period_number=candidate_slot.period_number,
                is_active=True,
            ).exists()

            if not b_busy_at_a and not a_busy_at_b:
                options.append({
                    "teacher": candidate_slot.teacher,
                    "slot": candidate_slot,
                    "same_subject": candidate_slot.subject == slot.subject,
                })
        return options

    @staticmethod
    @transaction.atomic
    def create_swap_request(
        school: "School",
        teacher_a: "CustomUser",
        teacher_b: "CustomUser",
        slot_a: ScheduleSlot,
        slot_b: ScheduleSlot,
        swap_date_a: date,
        swap_date_b: date,
        reason: str = "",
        requested_by: "CustomUser | None" = None,
    ) -> TeacherSwap:
        """إنشاء طلب تبديل + التحقق من القوانين + إرسال إشعار للمعلم ب."""
        # ── التحقق من القوانين ─────────────────────────────────
        errors = SwapService.validate_swap_request(
            teacher=teacher_a,
            slot_a=slot_a,
            slot_b=slot_b,
            swap_date=swap_date_a,
            school=school,
        )
        if errors:
            raise ValueError(" | ".join(errors))

        swap_type = "same_day" if swap_date_a == swap_date_b else "cross_day"
        swap = TeacherSwap.objects.create(
            school=school,
            teacher_a=teacher_a,
            teacher_b=teacher_b,
            slot_a=slot_a,
            slot_b=slot_b,
            swap_date_a=swap_date_a,
            swap_date_b=swap_date_b,
            swap_type=swap_type,
            status="pending_b",
            requested_by=requested_by or teacher_a,
            reason=reason,
        )
        # إشعار المعلم ب
        SwapService._notify(
            swap, teacher_b,
            title=f"طلب تبديل حصة من {teacher_a.full_name}",
            body=f"يطلب منك تبديل حصته ({slot_a.subject or 'حصة'}) بحصتك ({slot_b.subject or 'حصة'})",
            event_type="swap_request",
        )
        logger.info("SwapService: created swap %s (%s <-> %s)", swap.pk, teacher_a.full_name, teacher_b.full_name)
        return swap

    @staticmethod
    @transaction.atomic
    def respond_to_swap(swap: TeacherSwap, accepted: bool, rejection_reason: str = "") -> TeacherSwap:
        """المعلم ب يقبل أو يرفض."""
        from django.utils import timezone as tz

        if swap.status != "pending_b":
            raise ValueError(f"لا يمكن الرد على طلب بحالة: {swap.get_status_display()}")

        swap.b_responded_at = tz.now()
        if accepted:
            # تحديد المرحلة التالية
            if swap.is_cross_department:
                swap.status = "pending_vp"
            else:
                swap.status = "pending_coordinator"
            SwapService._notify(
                swap, swap.teacher_a,
                title=f"{swap.teacher_b.full_name} وافق على التبديل",
                body="بانتظار موافقة المنسق",
                event_type="swap_response",
            )
        else:
            swap.status = "rejected_b"
            swap.rejection_reason = rejection_reason
            SwapService._notify(
                swap, swap.teacher_a,
                title=f"{swap.teacher_b.full_name} رفض التبديل",
                body=rejection_reason or "يمكنك اختيار معلم آخر",
                event_type="swap_response",
            )
        swap.save()
        return swap

    @staticmethod
    @transaction.atomic
    def approve_swap(swap: TeacherSwap, approved_by: "CustomUser", approved: bool = True, rejection_reason: str = "") -> TeacherSwap:
        """المنسق أو النائب يوافق/يرفض."""
        from django.utils import timezone as tz

        valid_statuses = ("pending_coordinator", "pending_vp", "accepted_b")
        if swap.status not in valid_statuses:
            raise ValueError(f"لا يمكن اعتماد طلب بحالة: {swap.get_status_display()}")

        swap.approved_by = approved_by
        swap.approved_at = tz.now()

        if approved:
            swap.status = "approved"
            # تنفيذ تلقائي
            SwapService.execute_swap(swap)
        else:
            swap.status = "rejected"
            swap.rejection_reason = rejection_reason
            # إشعار الطرفين
            for t in (swap.teacher_a, swap.teacher_b):
                SwapService._notify(
                    swap, t,
                    title="تم رفض طلب التبديل",
                    body=rejection_reason or "تم رفض الطلب من الإدارة",
                    event_type="swap_response",
                )
        swap.save()
        return swap

    @staticmethod
    @transaction.atomic
    def execute_swap(swap: TeacherSwap) -> None:
        """تنفيذ التبديل الفعلي — تبديل المعلمين في الحصتين."""
        from django.utils import timezone as tz

        # تبديل المعلمين في ScheduleSlot
        slot_a = swap.slot_a
        slot_b = swap.slot_b
        slot_a.teacher, slot_b.teacher = slot_b.teacher, slot_a.teacher
        slot_a.save(update_fields=["teacher"])
        slot_b.save(update_fields=["teacher"])

        # تحديث Session اليومية إذا وُجدت
        Session.objects.filter(
            school=swap.school, teacher=swap.teacher_a,
            date=swap.swap_date_a, start_time=slot_a.start_time,
        ).update(teacher=swap.teacher_b)

        Session.objects.filter(
            school=swap.school, teacher=swap.teacher_b,
            date=swap.swap_date_b, start_time=slot_b.start_time,
        ).update(teacher=swap.teacher_a)

        swap.status = "executed"
        swap.executed_at = tz.now()
        swap.save(update_fields=["status", "executed_at"])

        # إشعار الطرفين
        for t in (swap.teacher_a, swap.teacher_b):
            SwapService._notify(
                swap, t,
                title="تم تنفيذ التبديل بنجاح",
                body=f"التبديل بين {swap.teacher_a.full_name} و {swap.teacher_b.full_name} تم",
                event_type="swap_approved",
            )
        logger.info("SwapService: executed swap %s", swap.pk)

    @staticmethod
    @transaction.atomic
    def force_swap(
        school: "School",
        teacher_a: "CustomUser",
        teacher_b: "CustomUser",
        slot_a: ScheduleSlot,
        slot_b: ScheduleSlot,
        swap_date_a: date,
        swap_date_b: date,
        forced_by: "CustomUser",
        reason: str = "",
    ) -> TeacherSwap:
        """نائب/مدير ينشئ وينفذ تبديل مباشرة بدون مسار موافقة."""
        swap_type = "same_day" if swap_date_a == swap_date_b else "cross_day"
        swap = TeacherSwap.objects.create(
            school=school,
            teacher_a=teacher_a,
            teacher_b=teacher_b,
            slot_a=slot_a,
            slot_b=slot_b,
            swap_date_a=swap_date_a,
            swap_date_b=swap_date_b,
            swap_type=swap_type,
            status="approved",
            requested_by=forced_by,
            approved_by=forced_by,
            reason=reason,
        )
        SwapService.execute_swap(swap)
        return swap

    # ── إلغاء الطلب (القانون 9 / 12-14) ─────────────────────────

    @staticmethod
    @transaction.atomic
    def cancel_swap(swap: TeacherSwap, cancelled_by: "CustomUser") -> TeacherSwap:
        """
        إلغاء طلب تبديل:
        - قبل رد المعلم ب → المعلم أ يلغي بحرية
        - بعد رد المعلم ب وقبل المنسق → أي طرف يطلب سحب
        - بعد موافقة المنسق → المنسق/النائب/المدير فقط
        """
        role = cancelled_by.get_role()
        is_leadership = role in ("coordinator", "principal", "vice_academic", "vice_admin")

        if swap.status == "pending_b":
            # القانون 12: المعلم أ يلغي بحرية
            if cancelled_by != swap.teacher_a and not is_leadership:
                raise ValueError("فقط المعلم صاحب الطلب يمكنه الإلغاء في هذه المرحلة")
        elif swap.status in ("accepted_b", "pending_coordinator", "pending_vp"):
            # القانون 13: أي طرف أو القيادة
            if cancelled_by not in (swap.teacher_a, swap.teacher_b) and not is_leadership:
                raise ValueError("فقط أحد المعلمين أو القيادة يمكنهم السحب")
        elif swap.status == "approved":
            # القانون 14: القيادة فقط
            if not is_leadership:
                raise ValueError("بعد الموافقة — فقط المنسق أو النائب أو المدير يمكنه الإلغاء")
        else:
            raise ValueError(f"لا يمكن إلغاء طلب بحالة: {swap.get_status_display()}")

        swap.status = "cancelled"
        swap.notes = f"ألغاه: {cancelled_by.full_name}"
        swap.save(update_fields=["status", "notes", "updated_at"])

        # إشعار الطرفين
        for t in (swap.teacher_a, swap.teacher_b):
            if t != cancelled_by:
                SwapService._notify(
                    swap, t,
                    title="تم إلغاء طلب التبديل",
                    body=f"قام {cancelled_by.full_name} بإلغاء الطلب",
                    event_type="swap_cancelled",
                )
        logger.info("SwapService: cancelled swap %s by %s", swap.pk, cancelled_by.full_name)
        return swap

    # ── انتهاء صلاحية الطلبات المعلّقة (القانون 7) ────────────────

    @staticmethod
    def expire_stale_swaps() -> int:
        """
        يُنفّذ دورياً (cron/management command) —
        يُلغي الطلبات المعلّقة أكثر من 48 ساعة بدون رد من المعلم ب.
        """
        from datetime import timedelta
        from django.utils import timezone as tz

        cutoff = tz.now() - timedelta(hours=SwapService.EXPIRY_HOURS)
        stale = TeacherSwap.objects.filter(
            status="pending_b",
            created_at__lt=cutoff,
        )
        count = stale.count()
        for swap in stale:
            swap.status = "cancelled"
            swap.notes = "انتهت صلاحية الطلب — لم يرد المعلم خلال 48 ساعة"
            swap.save(update_fields=["status", "notes", "updated_at"])
            SwapService._notify(
                swap, swap.teacher_a,
                title="انتهت صلاحية طلب التبديل",
                body=f"لم يرد {swap.teacher_b.full_name} خلال 48 ساعة — يمكنك تقديم طلب جديد",
                event_type="swap_expired",
            )
        if count:
            logger.info("SwapService: expired %d stale swaps", count)
        return count

    @staticmethod
    def _notify(swap: TeacherSwap, recipient: "CustomUser", title: str, body: str, event_type: str):
        """إرسال إشعار — يفشل بصمت إذا نظام الإشعارات غير متاح."""
        try:
            from notifications.hub import NotificationHub
            NotificationHub.dispatch(
                event_type=event_type,
                school=swap.school,
                recipients=[recipient],
                title=title,
                body=body,
                related_url="/teacher/schedule/swaps/",
            )
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            logger.warning("SwapService._notify failed [swap=%s]: %s", swap.pk, exc)


class CompensatoryService:
    """خدمة الحصص التعويضية."""

    @staticmethod
    def get_available_compensatory_slots(
        teacher: "CustomUser",
        school: "School",
        target_date: date,
        academic_year: str = settings.CURRENT_ACADEMIC_YEAR,
    ) -> list:
        """
        الأوقات المتاحة للتعويض — حصص حرة للمعلم في اليوم المطلوب.
        يتحقق أيضاً أن الشعبة ليست مشغولة.
        """
        from datetime import timedelta

        mapping = {6: 0, 0: 1, 1: 2, 2: 3, 3: 4}
        day = mapping.get(target_date.weekday(), -1)
        if day == -1:
            return []

        # حصص المعلم الحرة في هذا اليوم
        free = FreeSlotRegistry.objects.filter(
            teacher=teacher, school=school,
            day_of_week=day, academic_year=academic_year,
            is_available=True,
        ).values_list("period_number", flat=True)

        return sorted(free)

    @staticmethod
    @transaction.atomic
    def request_compensatory(
        school: "School",
        teacher: "CustomUser",
        original_slot: ScheduleSlot,
        absence: TeacherAbsence,
        compensatory_date: date,
        compensatory_period: int,
        notes: str = "",
    ) -> CompensatorySession:
        """إنشاء طلب تعويض + إشعار المنسق."""
        from datetime import timedelta

        # حساب week_offset
        original_date = absence.date
        diff_days = (compensatory_date - original_date).days
        week_offset = 1 if diff_days > 7 else 0

        if week_offset > 1:
            raise ValueError("الحد الأقصى للتعويض أسبوع واحد")

        comp = CompensatorySession.objects.create(
            school=school,
            teacher=teacher,
            original_slot=original_slot,
            absence=absence,
            compensatory_date=compensatory_date,
            compensatory_period=compensatory_period,
            class_group=original_slot.class_group,
            subject=original_slot.subject,
            week_offset=week_offset,
            status="pending",
            notes=notes,
        )

        # إشعار المنسق (إذا وُجد)
        try:
            from core.models import Membership
            from notifications.hub import NotificationHub

            dept = teacher.department
            if dept:
                coordinators = Membership.objects.filter(
                    school=school, is_active=True,
                    role__name="coordinator", department=dept,
                ).values_list("user_id", flat=True)

                from core.models import CustomUser
                coord_users = list(CustomUser.objects.filter(pk__in=coordinators))
                if coord_users:
                    NotificationHub.dispatch(
                        event_type="compensatory",
                        school=school,
                        recipients=coord_users,
                        title=f"طلب تعويض من {teacher.full_name}",
                        body=f"يطلب تعويض حصة {original_slot.subject or 'مادة'} بتاريخ {compensatory_date}",
                        related_url="/teacher/schedule/compensatory/",
                    )
        except (ImportError, OSError):
            pass

        logger.info("CompensatoryService: created request %s for teacher %s", comp.pk, teacher.full_name)
        return comp

    @staticmethod
    @transaction.atomic
    def approve_compensatory(
        comp: CompensatorySession,
        approved_by: "CustomUser",
        approved: bool = True,
        rejection_reason: str = "",
    ) -> CompensatorySession:
        """المنسق/النائب يوافق على التعويض — ينشئ Session تلقائياً."""
        from django.utils import timezone as tz

        if comp.status != "pending":
            raise ValueError(f"لا يمكن اعتماد طلب بحالة: {comp.get_status_display()}")

        comp.approved_by = approved_by
        comp.approved_at = tz.now()

        if approved:
            comp.status = "approved"

            # إنشاء Session فعلية
            from operations.models import TimeSlotConfig
            time_config = TimeSlotConfig.objects.filter(
                school=comp.school, period_number=comp.compensatory_period,
                day_type="regular", is_break=False,
            ).first()

            if time_config:
                session, _ = Session.objects.get_or_create(
                    school=comp.school,
                    teacher=comp.teacher,
                    class_group=comp.class_group,
                    date=comp.compensatory_date,
                    start_time=time_config.start_time,
                    defaults={
                        "subject": comp.subject,
                        "end_time": time_config.end_time,
                        "status": "scheduled",
                        "notes": f"حصة تعويضية — أصلية: {comp.original_slot}",
                    },
                )
                comp.session_created = session

            # تحديث FreeSlotRegistry — حجز الحصة وربطها بالتعويض
            mapping = {6: 0, 0: 1, 1: 2, 2: 3, 3: 4}
            our_day = mapping.get(comp.compensatory_date.weekday(), -1)
            if our_day >= 0:
                FreeSlotRegistry.objects.filter(
                    teacher=comp.teacher, school=comp.school,
                    day_of_week=our_day, period_number=comp.compensatory_period,
                ).update(is_available=False, reserved_for=comp)
        else:
            comp.status = "cancelled"
            comp.notes = f"{comp.notes}\nسبب الرفض: {rejection_reason}".strip()

        comp.save()

        # إشعار المعلم
        try:
            from notifications.hub import NotificationHub
            status_text = "تمت الموافقة" if approved else "تم الرفض"
            NotificationHub.dispatch(
                event_type="compensatory",
                school=comp.school,
                recipients=[comp.teacher],
                title=f"طلب التعويض: {status_text}",
                body=f"حصة {comp.subject or 'مادة'} بتاريخ {comp.compensatory_date}",
                related_url="/teacher/schedule/compensatory/",
            )
        except (ImportError, OSError, RuntimeError, ValueError):
            pass

        return comp

    @staticmethod
    @transaction.atomic
    def complete_compensatory(comp: CompensatorySession) -> CompensatorySession:
        """إكمال الحصة التعويضية بعد تسجيل الحضور."""
        if comp.status != "approved":
            raise ValueError("الحصة ليست معتمدة بعد")
        comp.status = "completed"
        comp.save(update_fields=["status", "updated_at"])
        return comp

    @staticmethod
    def expire_overdue(school: "School") -> int:
        """إلغاء الحصص التعويضية التي انتهت مهلتها (أكثر من أسبوعين)."""
        from datetime import timedelta
        cutoff = date.today() - timedelta(days=14)
        updated = CompensatorySession.objects.filter(
            school=school, status="pending",
            created_at__date__lt=cutoff,
        ).update(status="expired")
        if updated:
            logger.info("CompensatoryService.expire_overdue: expired %d requests", updated)
        return updated
