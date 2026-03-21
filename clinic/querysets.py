"""
clinic/querysets.py — Custom QuerySets للعيادة المدرسية
========================================================
"""
from __future__ import annotations

from django.db.models import Count, Q, QuerySet
from django.utils import timezone


class ClinicVisitQuerySet(QuerySet):
    """QuerySet لـ ClinicVisit."""

    def today(self) -> "ClinicVisitQuerySet":
        return self.filter(visit_date=timezone.now().date())

    def this_week(self) -> "ClinicVisitQuerySet":
        today = timezone.now().date()
        start = today - timezone.timedelta(days=today.weekday())
        return self.filter(visit_date__gte=start)

    def this_month(self) -> "ClinicVisitQuerySet":
        today = timezone.now().date()
        return self.filter(visit_date__year=today.year, visit_date__month=today.month)

    def date_range(self, start, end) -> "ClinicVisitQuerySet":
        return self.filter(visit_date__gte=start, visit_date__lte=end)

    def for_student(self, student) -> "ClinicVisitQuerySet":
        return self.filter(student=student)

    def sent_home(self) -> "ClinicVisitQuerySet":
        return self.filter(sent_home=True)

    def parent_notified(self) -> "ClinicVisitQuerySet":
        return self.filter(parent_notified=True)

    def needs_notification(self) -> "ClinicVisitQuerySet":
        """زيارات تحتاج إشعار ولي الأمر ولم تُرسَل بعد."""
        return self.filter(sent_home=True, parent_notified=False)

    def with_details(self) -> "ClinicVisitQuerySet":
        return self.select_related(
            "student",
            "student__profile",
            "nurse",
        )

    def frequent_visitors(self, threshold: int = 3):
        """الطلاب الذين زاروا العيادة أكثر من threshold مرة هذا الشهر."""
        today = timezone.now().date()
        return (
            self.filter(visit_date__year=today.year, visit_date__month=today.month)
            .values("student__id", "student__full_name")
            .annotate(visit_count=Count("id"))
            .filter(visit_count__gte=threshold)
            .order_by("-visit_count")
        )
