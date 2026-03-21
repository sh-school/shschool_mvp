"""
quality/querysets.py — Custom QuerySets للخطة التشغيلية والجودة
================================================================
"""
from __future__ import annotations

from django.db.models import Avg, Count, F, Q, QuerySet
from django.utils import timezone


class ProcedureQuerySet(QuerySet):
    """QuerySet لـ OperationalProcedure."""

    # ── الفلترة حسب الحالة ────────────────────────────────────────────────

    def not_started(self) -> "ProcedureQuerySet":
        return self.filter(status="not_started")

    def in_progress(self) -> "ProcedureQuerySet":
        return self.filter(status="in_progress")

    def pending_review(self) -> "ProcedureQuerySet":
        return self.filter(status="pending_review")

    def completed(self) -> "ProcedureQuerySet":
        return self.filter(status="completed")

    def cancelled(self) -> "ProcedureQuerySet":
        return self.filter(status="cancelled")

    def active(self) -> "ProcedureQuerySet":
        return self.exclude(status__in=["completed", "cancelled"])

    # ── الفلترة الزمنية ────────────────────────────────────────────────────

    def overdue(self) -> "ProcedureQuerySet":
        """تجاوزت الموعد ولم تكتمل."""
        return self.active().filter(deadline__lt=timezone.now().date())

    def due_soon(self, days: int = 7) -> "ProcedureQuerySet":
        """تنتهي خلال n أيام."""
        today = timezone.now().date()
        deadline = today + timezone.timedelta(days=days)
        return self.active().filter(deadline__gte=today, deadline__lte=deadline)

    def due_this_month(self) -> "ProcedureQuerySet":
        today = timezone.now().date()
        return self.active().filter(
            deadline__year=today.year,
            deadline__month=today.month,
        )

    # ── الفلترة حسب المنفذ ────────────────────────────────────────────────

    def for_executor(self, user) -> "ProcedureQuerySet":
        return self.filter(executor_user=user)

    def for_domain(self, domain) -> "ProcedureQuerySet":
        return self.filter(indicator__target__domain=domain)

    # ── تحسين الـ queries ─────────────────────────────────────────────────

    def with_details(self) -> "ProcedureQuerySet":
        return self.select_related(
            "indicator",
            "indicator__target",
            "indicator__target__domain",
            "executor_user",
        ).prefetch_related("evidence")

    # ── الإحصاء ───────────────────────────────────────────────────────────

    def completion_rate(self) -> float:
        total = self.count()
        if not total:
            return 0.0
        done = self.completed().count()
        return round(done / total * 100, 1)

    def summary_by_status(self):
        return self.values("status").annotate(count=Count("id")).order_by("status")

    def executor_ranking(self):
        """ترتيب المنفذين حسب نسبة الإنجاز."""
        return (
            self.values(
                "executor_user__id",
                "executor_user__full_name",
            )
            .annotate(
                total=Count("id"),
                done=Count("id", filter=Q(status="completed")),
            )
            .order_by("-done")
        )


class DomainQuerySet(QuerySet):
    """QuerySet لـ OperationalDomain."""

    def with_progress(self) -> "DomainQuerySet":
        """يضيف نسبة الإنجاز لكل مجال."""
        return self.annotate(
            total_procedures=Count("targets__indicators__procedures"),
            completed_procedures=Count(
                "targets__indicators__procedures",
                filter=Q(targets__indicators__procedures__status="completed"),
            ),
        )

    def with_all(self) -> "DomainQuerySet":
        return self.prefetch_related(
            "targets",
            "targets__indicators",
            "targets__indicators__procedures",
        )
