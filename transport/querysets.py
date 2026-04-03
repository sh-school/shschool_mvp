"""
transport/querysets.py — Custom QuerySets للنقل المدرسي
========================================================
"""

from __future__ import annotations

from django.db.models import Count, F, QuerySet


class BusQuerySet(QuerySet):
    """QuerySet لـ SchoolBus."""

    def for_school(self, school) -> BusQuerySet:
        return self.filter(school=school)

    def with_supervisor(self) -> BusQuerySet:
        return self.filter(supervisor__isnull=False)

    def without_supervisor(self) -> BusQuerySet:
        return self.filter(supervisor__isnull=True)

    def overcapacity(self) -> BusQuerySet:
        """حافلات تجاوزت الطاقة الاستيعابية."""
        return self.annotate(student_count=Count("routes__students")).filter(
            student_count__gt=F("capacity")
        )

    def with_details(self) -> BusQuerySet:
        return self.select_related("supervisor").prefetch_related("routes")


class RouteQuerySet(QuerySet):
    """QuerySet لـ BusRoute."""

    def for_school(self, school) -> RouteQuerySet:
        return self.filter(school=school)

    def for_area(self, area: str) -> RouteQuerySet:
        return self.filter(area_name__icontains=area)

    def with_students(self) -> RouteQuerySet:
        return self.prefetch_related("students")

    def student_count(self) -> RouteQuerySet:
        return self.annotate(num_students=Count("students"))
