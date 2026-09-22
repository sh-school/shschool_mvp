"""operations/services/substitute.py — البدلاء وإسناد الحصص عند غياب المعلّم.

منقولٌ حرفيّاً من `operations/services.py` (البند 8)؛ لا تغيير في المنطق.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

from django.db import models, transaction
from django.db.models import QuerySet

from operations.models import (
    ScheduleSlot,
    Session,
    SubjectClassAssignment,
    SubstituteAssignment,
    TeacherAbsence,
    TeacherExemption,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.models import CustomUser, School


class SubstituteService:
    @staticmethod
    def get_available_teachers(
        school: School,
        date: date,
        day_of_week: int,
        period_number: int,
        exclude_teacher: CustomUser | None = None,
        subject_id: int | None = None,
    ) -> QuerySet:
        """
        إيجاد معلمين متاحين للبدل:
        - لديهم membership نشطة في المدرسة
        - ليس لديهم حصة في نفس اليوم والحصة
        - لم يُسجَّل غيابهم في نفس اليوم

        إذا تم تمرير subject_id، يُرتَّب المعلمون بحيث يظهر
        معلمو نفس المادة أولاً ثم البقية.
        """
        from core.models import Membership

        # جميع معلمي المدرسة
        teacher_ids = Membership.objects.filter(
            school=school, is_active=True, role__name__in=("teacher", "coordinator")
        ).values_list("user_id", flat=True)

        if exclude_teacher:
            teacher_ids = [t for t in teacher_ids if t != exclude_teacher.id]

        # من لديهم حصة في نفس الوقت
        # والعامُ قيدٌ: معلّمٌ له حصّةٌ في جدول عامٍ مضى كان يُعدّ مشغولاً
        # فيُستبعد من البدلاء وهو متفرّغ.
        busy_ids = (
            ScheduleSlot.objects.live(school)
            .filter(day_of_week=day_of_week, period_number=period_number)
            .values_list("teacher_id", flat=True)
        )

        # من هم غائبون في نفس اليوم
        absent_ids = TeacherAbsence.objects.filter(school=school, date=date).values_list(
            "teacher_id", flat=True
        )

        # ومن فُرّغ في هذه الخانة بقرارٍ ملزم — وكان البديلُ يتجاهل التفريغَ كلَّه،
        # فيُقترح معلّمٌ أخرجته الوزارةُ من الحصّة. أمّا تفريغُ «لتوليد الجدول»
        # فيُوسَم ولا يمنع: صاحبُه رُتّب له جدولُه ولم يُمنَع من الحصّة.
        exempt_ids = SubstituteService.exempted_teacher_ids(school, day_of_week, period_number)

        available_ids = set(teacher_ids) - set(busy_ids) - set(absent_ids) - exempt_ids

        from core.models import CustomUser

        qs = CustomUser.objects.filter(id__in=available_ids)

        if subject_id:
            from django.db.models import Case, IntegerField, Value, When

            same_subject_ids = set(
                SubjectClassAssignment.objects.live(school)
                .filter(subject_id=subject_id, teacher_id__in=available_ids)
                .values_list("teacher_id", flat=True)
            )
            qs = qs.annotate(
                same_subject=Case(
                    When(id__in=same_subject_ids, then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            ).order_by("same_subject", "full_name")
        else:
            qs = qs.order_by("full_name")

        return qs

    @staticmethod
    def exempted_teacher_ids(school: School, day_of_week: int, period_number: int) -> set:
        """من لا يجوز إشغالُه في هذه الخانة بحكم تفريغٍ ملزم.

        يومٌ كاملٌ أو الحصّةُ بعينها، من عام المدرسة الجاري، وبجهةٍ تُلزم —
        فتفريغُ «لتوليد الجدول» لا يدخل هنا (`TeacherExemption.SOFT_SOURCES`).
        """
        from core.querysets import year_or_current

        rows = TeacherExemption.objects.filter(
            school=school,
            academic_year=year_or_current(school),
            is_active=True,
            day_of_week=day_of_week,
        ).exclude(source__in=TeacherExemption.SOFT_SOURCES)
        rows = rows.filter(
            models.Q(exemption_type="full_day") | models.Q(period_number=period_number)
        )
        return set(rows.values_list("teacher_id", flat=True))

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
        total_slots = (
            ScheduleSlot.objects.live(absence.school)
            .filter(
                teacher=absence.teacher,
                day_of_week=SubstituteService._date_to_day(absence.date),
            )
            .count()
        )
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
        substitute: CustomUser,
        assigned_by: CustomUser | None = None,
        notes: str = "",
    ) -> SubstituteAssignment:
        """
        تعيين بديل + تحديث Session.teacher (الفجوة الحرجة المكتشفة).
        يضمن أن الحصة اليومية تعكس المعلم الفعلي.
        """
        assignment = SubstituteService.assign_substitute(
            absence,
            slot,
            substitute,
            assigned_by,
            notes,
        )
        # تحديث Session اليومية إذا وُجدت
        Session.objects.filter(
            school=absence.school,
            teacher=absence.teacher,
            date=absence.date,
            start_time=slot.start_time,
        ).update(teacher=substitute)
        return assignment
