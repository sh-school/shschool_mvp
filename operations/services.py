from django.db import transaction
from django.utils import timezone
from django.db.models import Count, Q
from operations.models import Session, StudentAttendance, AbsenceAlert, ScheduleSlot, TeacherAbsence, SubstituteAssignment
from core.models import StudentEnrollment


class AttendanceService:
    @staticmethod
    @transaction.atomic
    def mark_attendance(session, student, status, excuse_type="", excuse_notes="", marked_by=None):
        att, created = StudentAttendance.objects.update_or_create(
            session=session,
            student=student,
            defaults={
                "school":       session.school,
                "status":       status,
                "excuse_type":  excuse_type,
                "excuse_notes": excuse_notes,
                "marked_by":    marked_by,
            }
        )
        # Check absence threshold
        if status == "absent":
            AttendanceService.check_absence_threshold(student, session.school)
        return att, created

    @staticmethod
    @transaction.atomic
    def bulk_mark_all_present(session, marked_by=None):
        students = StudentEnrollment.objects.filter(
            class_group=session.class_group, is_active=True
        ).select_related("student")

        records = []
        for enrollment in students:
            records.append(StudentAttendance(
                session=session,
                student=enrollment.student,
                school=session.school,
                status="present",
                marked_by=marked_by,
            ))
        StudentAttendance.objects.bulk_create(records, ignore_conflicts=True)
        session.status = "in_progress"
        session.save(update_fields=["status"])
        return len(records)

    @staticmethod
    @transaction.atomic
    def complete_session(session):
        session.status = "completed"
        session.save(update_fields=["status"])

    @staticmethod
    def check_absence_threshold(student, school, threshold=3):
        from datetime import timedelta
        today   = timezone.now().date()
        week_ago = today - timedelta(days=7)

        consecutive = StudentAttendance.objects.filter(
            student=student,
            school=school,
            status="absent",
            session__date__gte=week_ago,
            session__date__lte=today,
        ).count()

        if consecutive >= threshold:
            AbsenceAlert.objects.get_or_create(
                school=school,
                student=student,
                status="pending",
                period_start=week_ago,
                period_end=today,
                defaults={"absence_count": consecutive}
            )

    @staticmethod
    def get_session_summary(session):
        att = StudentAttendance.objects.filter(session=session)
        total   = att.count()
        present = att.filter(status="present").count()
        absent  = att.filter(status="absent").count()
        late    = att.filter(status="late").count()
        excused = att.filter(status="excused").count()
        pct     = round(present / total * 100) if total else 0
        return {"total": total, "present": present, "absent": absent,
                "late": late, "excused": excused, "percentage": pct}


# ─────────────────────────────────────────────
# المرحلة 2 — الجداول الذكية + نظام البديل
# ─────────────────────────────────────────────

class ScheduleService:

    # ── الجدول الأسبوعي ──────────────────────

    @staticmethod
    def get_weekly_schedule(school, teacher=None, class_group=None, academic_year="2025-2026"):
        """إرجاع الجدول الأسبوعي مرتّباً حسب اليوم والحصة"""
        qs = ScheduleSlot.objects.filter(
            school=school, academic_year=academic_year, is_active=True
        ).select_related("teacher", "class_group", "subject")
        if teacher:
            qs = qs.filter(teacher=teacher)
        if class_group:
            qs = qs.filter(class_group=class_group)

        # بناء matrix: {يوم: {رقم_حصة: slot}}
        grid = {d: {} for d in range(5)}   # 0=أحد … 4=خميس
        for slot in qs:
            grid[slot.day_of_week][slot.period_number] = slot
        return grid

    @staticmethod
    def detect_conflicts(school, academic_year="2025-2026"):
        """كشف التعارضات في الجدول"""
        conflicts = []

        # تعارض المعلم: نفس المعلم في نفس اليوم والحصة
        teacher_dups = (
            ScheduleSlot.objects.filter(school=school, academic_year=academic_year, is_active=True)
            .values("teacher", "day_of_week", "period_number")
            .annotate(cnt=Count("id"))
            .filter(cnt__gt=1)
        )
        for dup in teacher_dups:
            slots = ScheduleSlot.objects.filter(
                school=school, teacher_id=dup["teacher"],
                day_of_week=dup["day_of_week"],
                period_number=dup["period_number"],
                is_active=True
            ).select_related("teacher", "class_group")
            conflicts.append({
                "type": "teacher",
                "message": f"تعارض معلم: {slots[0].teacher.full_name} — {slots[0].day_name} ح{dup['period_number']}",
                "slots": list(slots),
            })

        # تعارض الفصل: نفس الفصل في نفس اليوم والحصة
        class_dups = (
            ScheduleSlot.objects.filter(school=school, academic_year=academic_year, is_active=True)
            .values("class_group", "day_of_week", "period_number")
            .annotate(cnt=Count("id"))
            .filter(cnt__gt=1)
        )
        for dup in class_dups:
            slots = ScheduleSlot.objects.filter(
                school=school, class_group_id=dup["class_group"],
                day_of_week=dup["day_of_week"],
                period_number=dup["period_number"],
                is_active=True
            ).select_related("teacher", "class_group")
            conflicts.append({
                "type": "class",
                "message": f"تعارض فصل: {slots[0].class_group} — {slots[0].day_name} ح{dup['period_number']}",
                "slots": list(slots),
            })

        return conflicts

    @staticmethod
    @transaction.atomic
    def generate_daily_sessions(school, date, academic_year="2025-2026"):
        """توليد Session يومية من ScheduleSlot للتاريخ المحدد"""
        day_of_week = date.weekday()   # Python: 0=Mon … لكننا نريد 0=Sun
        # تحويل: Sun=6 في Python → 0 عندنا
        mapping = {6: 0, 0: 1, 1: 2, 2: 3, 3: 4}
        our_day = mapping.get(day_of_week, -1)
        if our_day == -1:
            return 0  # جمعة أو سبت

        slots = ScheduleSlot.objects.filter(
            school=school, day_of_week=our_day,
            academic_year=academic_year, is_active=True
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
                    "subject":    slot.subject,
                    "end_time":   slot.end_time,
                    "status":     "scheduled",
                }
            )
            if was_created:
                created += 1
        return created


class SubstituteService:

    @staticmethod
    def get_available_teachers(school, date, day_of_week, period_number, exclude_teacher=None):
        """
        إيجاد معلمين متاحين للبدل:
        - لديهم membership نشطة في المدرسة
        - ليس لديهم حصة في نفس اليوم والحصة
        - لم يُسجَّل غيابهم في نفس اليوم
        """
        from core.models import Membership
        # جميع معلمي المدرسة
        teacher_ids = Membership.objects.filter(
            school=school, is_active=True,
            role__name__in=("teacher", "coordinator")
        ).values_list("user_id", flat=True)

        if exclude_teacher:
            teacher_ids = [t for t in teacher_ids if t != exclude_teacher.id]

        # من لديهم حصة في نفس الوقت
        busy_ids = ScheduleSlot.objects.filter(
            school=school, day_of_week=day_of_week,
            period_number=period_number, is_active=True
        ).values_list("teacher_id", flat=True)

        # من هم غائبون في نفس اليوم
        absent_ids = TeacherAbsence.objects.filter(
            school=school, date=date
        ).values_list("teacher_id", flat=True)

        available_ids = set(teacher_ids) - set(busy_ids) - set(absent_ids)

        from core.models import CustomUser
        return CustomUser.objects.filter(id__in=available_ids).order_by("full_name")

    @staticmethod
    @transaction.atomic
    def register_absence(school, teacher, date, reason, reason_notes="", reported_by=None):
        """تسجيل غياب معلم + إنشاء تعيينات البديل تلقائياً"""
        absence, created = TeacherAbsence.objects.get_or_create(
            school=school, teacher=teacher, date=date,
            defaults={
                "reason":       reason,
                "reason_notes": reason_notes,
                "reported_by":  reported_by,
                "status":       "pending",
            }
        )
        return absence

    @staticmethod
    @transaction.atomic
    def assign_substitute(absence, slot, substitute, assigned_by=None, notes=""):
        """تعيين بديل لحصة محددة"""
        assignment, created = SubstituteAssignment.objects.update_or_create(
            absence=absence, slot=slot,
            defaults={
                "substitute":  substitute,
                "school":      absence.school,
                "assigned_by": assigned_by,
                "notes":       notes,
                "status":      "assigned",
            }
        )
        # تحديث حالة الغياب
        total_slots = ScheduleSlot.objects.filter(
            school=absence.school,
            teacher=absence.teacher,
            day_of_week=SubstituteService._date_to_day(absence.date),
            is_active=True
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
    def _date_to_day(date):
        mapping = {6: 0, 0: 1, 1: 2, 2: 3, 3: 4}
        return mapping.get(date.weekday(), -1)

    @staticmethod
    def get_substitute_report(school, date_from, date_to):
        """تقرير الحصص البديلة في فترة"""
        return SubstituteAssignment.objects.filter(
            school=school,
            absence__date__range=(date_from, date_to)
        ).select_related(
            "substitute", "absence__teacher", "slot__class_group", "slot__subject"
        ).order_by("absence__date", "slot__period_number")
