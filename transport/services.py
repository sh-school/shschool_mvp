"""
transport/services.py — Business Logic لوحدة النقل المدرسي
═══════════════════════════════════════════════════════════
Service Layer — فصل الـ business logic عن الـ views.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.models import School


class TransportService:
    """خدمات النقل المدرسي — لوحة التحكم والإحصائيات."""

    @staticmethod
    def get_dashboard_context(school: School) -> dict:
        """
        السياق الكامل للوحة النقل — annotate بدل loop (N+1 fix مُحكَّم).

        ✅ v5.4: ينقل جميع queries من transport_dashboard view إلى service layer.

        Args:
            school: كائن المدرسة

        Returns:
            dict يحتوي: total_buses, total_capacity, total_students,
                        total_assigned, overall_occupancy, overcapacity_count,
                        no_supervisor, no_karwa, bus_data
        """
        from django.db.models import Count, Q, Sum

        from core.models import CustomUser, SchoolBus

        buses = (
            SchoolBus.objects.filter(school=school)
            .select_related("supervisor")
            .annotate(students_count=Count("routes__students", distinct=True))
        )

        totals = buses.aggregate(
            total_buses=Count("id"),
            total_capacity=Sum("capacity"),
        )
        total_buses = totals["total_buses"] or 0
        total_capacity = totals["total_capacity"] or 0

        total_students = (
            CustomUser.objects.filter(bus_routes__bus__school=school).distinct().count()
        )

        bus_data = [
            {
                "bus": bus,
                "students_count": bus.students_count,
                "occupancy_rate": (
                    round(bus.students_count / bus.capacity * 100) if bus.capacity > 0 else 0
                ),
            }
            for bus in buses
        ]

        total_assigned = sum(b["students_count"] for b in bus_data)
        overall_occupancy = round(total_assigned / total_capacity * 100) if total_capacity else 0
        overcapacity_count = sum(1 for b in bus_data if b["occupancy_rate"] > 100)
        no_supervisor = buses.filter(supervisor__isnull=True).count()
        no_karwa = buses.filter(Q(karwa_id="") | Q(karwa_id__isnull=True)).count()

        return {
            "total_buses": total_buses,
            "total_capacity": total_capacity,
            "total_students": total_students,
            "total_assigned": total_assigned,
            "overall_occupancy": overall_occupancy,
            "overcapacity_count": overcapacity_count,
            "no_supervisor": no_supervisor,
            "no_karwa": no_karwa,
            "bus_data": bus_data,
        }

    @staticmethod
    def get_statistics(school: School) -> dict:
        """
        إحصائيات النقل المدرسي — aggregate DB بدل Python sum loop.

        ✅ v5.4: يُصلح transport_statistics view (Python sum loop → DB aggregate).

        Args:
            school: كائن المدرسة

        Returns:
            dict يحتوي: total_buses, total_capacity, students_count,
                        utilization_rate, buses
        """
        from django.db.models import Sum

        from core.models import CustomUser, SchoolBus

        buses = SchoolBus.objects.filter(school=school).select_related("supervisor")
        agg = buses.aggregate(total_capacity=Sum("capacity", default=0))
        total_buses = buses.count()
        total_capacity = agg["total_capacity"] or 0

        students_count = (
            CustomUser.objects.filter(bus_routes__bus__school=school).distinct().count()
        )
        utilization_rate = (students_count / total_capacity * 100) if total_capacity > 0 else 0

        return {
            "total_buses": total_buses,
            "total_capacity": total_capacity,
            "students_count": students_count,
            "utilization_rate": round(utilization_rate, 1),
            "buses": buses,
        }
