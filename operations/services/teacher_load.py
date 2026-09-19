"""operations/services/teacher_load.py — أنصبة المعلّمين.

منقولٌ حرفيّاً من `operations/services.py` (البند 8)؛ لا تغيير في المنطق.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

from operations.models import (
    ScheduleSlot,
    SubstituteAssignment,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.models import School


class TeacherLoadService:
    """خدمات تقرير أحمال المعلمين — ينقل business logic من teacher_load_report view."""

    @staticmethod
    def get_teacher_load_data(school: School, year: str, teachers) -> dict:
        """
        بيانات تقرير أحمال المعلمين — استعلامان بدل N+1.

        ✅ v5.4: يستبدل Counter loop في teacher_load_report view:
          - استعلام واحد لـ slot_counts بدل N استعلامات
          - استعلام واحد لـ sub_counts الشهرية
          - daily_counts يُبنى من نفس rows ScheduleSlot

        Args:
            school: كائن المدرسة
            year: العام الدراسي
            teachers: QuerySet للمعلمين المستهدفين

        Returns:
            dict يحتوي: teacher_data (list), avg_weekly (float),
                        total_teachers (int)
        """
        from collections import Counter

        slot_counts = Counter(
            ScheduleSlot.objects.filter(
                school=school, academic_year=year, is_active=True
            ).values_list("teacher_id", flat=True)
        )
        month_start = date.today().replace(day=1)
        sub_counts = Counter(
            SubstituteAssignment.objects.filter(
                school=school, absence__date__gte=month_start
            ).values_list("substitute_id", flat=True)
        )

        # بناء daily_counts من نفس ScheduleSlot QuerySet — استعلام واحد
        daily_counts: dict[tuple, int] = {}
        for slot in ScheduleSlot.objects.filter(school=school, academic_year=year, is_active=True):
            key = (str(slot.teacher_id), slot.day_of_week)
            daily_counts[key] = daily_counts.get(key, 0) + 1

        teacher_data = []
        for t in teachers:
            tid = str(t.id)
            weekly = slot_counts.get(t.id, 0)
            subs = sub_counts.get(t.id, 0)
            days = [daily_counts.get((tid, d), 0) for d in range(5)]
            teacher_data.append(
                {
                    "teacher": t,
                    "weekly": weekly,
                    "subs": subs,
                    "max_daily": max(days) if days else 0,
                    "min_daily": min(d for d in days if d > 0) if any(d > 0 for d in days) else 0,
                    "free_days": sum(1 for d in days if d == 0),
                    "days": days,
                }
            )

        teacher_data.sort(key=lambda x: -x["weekly"])
        avg_weekly = (
            sum(d["weekly"] for d in teacher_data) / len(teacher_data) if teacher_data else 0
        )

        return {
            "teacher_data": teacher_data,
            "avg_weekly": round(avg_weekly, 1),
            "total_teachers": len(teacher_data),
        }
