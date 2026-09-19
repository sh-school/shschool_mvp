"""operations/services/compensatory.py — الحصص التعويضيّة.

منقولٌ حرفيّاً من `operations/services.py` (البند 8)؛ لا تغيير في المنطق.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

from django.db import transaction

from core.academic_calendar import (
    academic_year_for_school,
)
from operations.models import (
    CompensatorySession,
    FreeSlotRegistry,
    ScheduleSlot,
    Session,
    TeacherAbsence,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.models import CustomUser, School


class CompensatoryService:
    """خدمة الحصص التعويضية."""

    @staticmethod
    def get_available_compensatory_slots(
        teacher: CustomUser,
        school: School,
        target_date: date,
        academic_year: str | None = None,
    ) -> list:
        """
        الأوقات المتاحة للتعويض — حصص حرة للمعلم في اليوم المطلوب.
        يتحقق أيضاً أن الشعبة ليست مشغولة.
        """

        academic_year = academic_year or academic_year_for_school(school)
        mapping = {6: 0, 0: 1, 1: 2, 2: 3, 3: 4}
        day = mapping.get(target_date.weekday(), -1)
        if day == -1:
            return []

        # حصص المعلم الحرة في هذا اليوم
        free = FreeSlotRegistry.objects.filter(
            teacher=teacher,
            school=school,
            day_of_week=day,
            academic_year=academic_year,
            is_available=True,
        ).values_list("period_number", flat=True)

        return sorted(free)

    @staticmethod
    @transaction.atomic
    def request_compensatory(
        school: School,
        teacher: CustomUser,
        original_slot: ScheduleSlot,
        absence: TeacherAbsence,
        compensatory_date: date,
        compensatory_period: int,
        notes: str = "",
    ) -> CompensatorySession:
        """إنشاء طلب تعويض + إشعار المنسق."""

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
            from notifications.hub import NotificationHub

            dept_obj = teacher.department_obj
            if dept_obj:
                coordinators = dept_obj.memberships.filter(
                    is_active=True,
                    role__name="coordinator",
                ).values_list("user_id", flat=True)
            else:
                coordinators = []
            if coordinators:
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
            # الإشعار جانبيّ: فشلُه لا يُسقط إنشاء الطلب، لكنّه يُسجَّل لا يُبتلع.
            logger.warning("CompensatoryService: تعذّر إشعار المنسّقين بطلب التعويض")

        logger.info(
            "CompensatoryService: created request %s for teacher %s", comp.pk, teacher.full_name
        )
        return comp

    @staticmethod
    @transaction.atomic
    def approve_compensatory(
        comp: CompensatorySession,
        approved_by: CustomUser,
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
                school=comp.school,
                period_number=comp.compensatory_period,
                day_type="regular",
                is_break=False,
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
                    teacher=comp.teacher,
                    school=comp.school,
                    day_of_week=our_day,
                    period_number=comp.compensatory_period,
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
            # الإشعار جانبيّ: فشلُه لا يُلغي قرار الموافقة/الرفض، لكنّه يُسجَّل لا يُبتلع.
            logger.warning("CompensatoryService: تعذّر إشعار المعلّم بقرار التعويض")

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
    def expire_overdue(school: School) -> int:
        """إلغاء الحصص التعويضية التي انتهت مهلتها (أكثر من أسبوعين)."""
        from datetime import timedelta

        cutoff = date.today() - timedelta(days=14)
        updated = CompensatorySession.objects.filter(
            school=school,
            status="pending",
            created_at__date__lt=cutoff,
        ).update(status="expired")
        if updated:
            logger.info("CompensatoryService.expire_overdue: expired %d requests", updated)
        return updated
