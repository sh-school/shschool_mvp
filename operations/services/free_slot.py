"""operations/services/free_slot.py — سجلّ الحصص الشاغرة.

منقولٌ حرفيّاً من `operations/services.py` (البند 8)؛ لا تغيير في المنطق.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import QuerySet

from core.academic_calendar import (
    academic_year_for_school,
)
from operations.models import (
    FreeSlotRegistry,
    ScheduleSlot,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.models import CustomUser, School


# ═════════════════════════════════════════════════════════════════════
# المرحلة 4 — خدمات التبديل والتعويض والحصص الحرة
# ═════════════════════════════════════════════════════════════════════


class FreeSlotService:
    """خدمة سجل الحصص الحرة — يُبنى تلقائياً من فراغات ScheduleSlot."""

    @staticmethod
    @transaction.atomic
    def build_registry(
        school: School,
        academic_year: str | None = None,
        max_periods: int = 7,
    ) -> int:
        """
        بناء/إعادة بناء سجل الحصص الحرة لكل معلمي المدرسة.
        يمسح القديم ويبني من جديد بناءً على ScheduleSlot.
        """
        academic_year = academic_year or academic_year_for_school(school)
        from core.models import Membership

        # حذف السجل القديم
        FreeSlotRegistry.objects.filter(school=school, academic_year=academic_year).delete()

        # جميع معلمي المدرسة
        teacher_ids = list(
            Membership.objects.filter(
                school=school,
                is_active=True,
                role__name__in=("teacher", "coordinator", "ese_teacher"),
            ).values_list("user_id", flat=True)
        )

        # بناء مجموعة الحصص المشغولة لكل معلم
        busy = {}
        slots = ScheduleSlot.objects.filter(
            school=school,
            academic_year=academic_year,
            is_active=True,
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
                        records.append(
                            FreeSlotRegistry(
                                teacher_id=tid,
                                school=school,
                                day_of_week=day,
                                period_number=period,
                                academic_year=academic_year,
                                is_available=True,
                            )
                        )

        FreeSlotRegistry.objects.bulk_create(records, batch_size=500)
        logger.info(
            "FreeSlotService.build_registry: created %d entries for school %s",
            len(records),
            school.code,
        )
        return len(records)

    @staticmethod
    def get_teacher_free_slots(
        teacher: CustomUser,
        school: School,
        academic_year: str | None = None,
    ) -> QuerySet:
        """حصص المعلم الفارغة — مرتبة حسب اليوم والحصة."""
        academic_year = academic_year or academic_year_for_school(school)
        return FreeSlotRegistry.objects.filter(
            teacher=teacher,
            school=school,
            academic_year=academic_year,
            is_available=True,
        ).order_by("day_of_week", "period_number")

    @staticmethod
    def get_free_teachers_at(
        school: School,
        day_of_week: int,
        period_number: int,
        academic_year: str | None = None,
        department=None,
    ) -> QuerySet:
        """
        المعلمون المتاحون في وقت معيّن.
        department: كائن Department أو اسم نصي — يُرشّح حسب القسم.
        """
        academic_year = academic_year or academic_year_for_school(school)
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
            from core.models import Department

            if isinstance(department, Department):
                dept_teacher_ids = department.get_teacher_ids()
            else:
                # fallback: اسم نصي
                dept_teacher_ids = Membership.objects.filter(
                    school=school,
                    is_active=True,
                    department_obj__name=department,
                ).values_list("user_id", flat=True)
            teachers = teachers.filter(id__in=dept_teacher_ids)

        return teachers
