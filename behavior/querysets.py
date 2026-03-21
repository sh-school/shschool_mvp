"""
behavior/querysets.py — Custom QuerySets للسلوك الطلابي
=========================================================
"""
from __future__ import annotations

from django.db.models import Count, Q, QuerySet, Sum
from django.utils import timezone


class InfractionQuerySet(QuerySet):
    """QuerySet لـ BehaviorInfraction."""

    # ── الفلترة حسب الخطورة ────────────────────────────────────────────────

    def level(self, lvl: int) -> "InfractionQuerySet":
        return self.filter(level=lvl)

    def serious(self) -> "InfractionQuerySet":
        """مخالفات الدرجة 3 و 4 — خطيرة."""
        return self.filter(level__gte=3)

    def minor(self) -> "InfractionQuerySet":
        """مخالفات الدرجة 1 و 2."""
        return self.filter(level__lte=2)

    # ── الفلترة الزمنية ────────────────────────────────────────────────────

    def this_week(self) -> "InfractionQuerySet":
        today = timezone.now().date()
        start = today - timezone.timedelta(days=today.weekday())
        return self.filter(date__gte=start)

    def this_month(self) -> "InfractionQuerySet":
        today = timezone.now().date()
        return self.filter(date__year=today.year, date__month=today.month)

    def this_term(self, term_start=None) -> "InfractionQuerySet":
        if not term_start:
            today = timezone.now().date()
            # الفصل الأول: سبتمبر — يناير | الفصل الثاني: فبراير — يونيو
            if today.month >= 9:
                term_start = today.replace(month=9, day=1)
            else:
                term_start = today.replace(month=2, day=1)
        return self.filter(date__gte=term_start)

    def date_range(self, start, end) -> "InfractionQuerySet":
        return self.filter(date__gte=start, date__lte=end)

    # ── الفلترة حسب الطالب / الفصل ────────────────────────────────────────

    def for_student(self, student) -> "InfractionQuerySet":
        return self.filter(student=student)

    def for_class(self, class_group) -> "InfractionQuerySet":
        return self.filter(student__studentenrollment__class_group=class_group).distinct()

    # ── الطلاب في خطر الفصل ────────────────────────────────────────────────

    def at_risk(self, threshold: int = 80) -> "InfractionQuerySet":
        """
        الطلاب الذين تجاوزوا حد النقاط المخصومة — خطر الفصل.
        يُرجع queryset مُجمَّع على مستوى الطالب.
        """
        return (
            self.values("student")
            .annotate(total_points=Sum("points_deducted"))
            .filter(total_points__gte=threshold)
            .order_by("-total_points")
        )

    # ── تحسين الـ queries ─────────────────────────────────────────────────

    def with_student(self) -> "InfractionQuerySet":
        return self.select_related("student", "reported_by", "violation_category")

    def with_recovery(self) -> "InfractionQuerySet":
        return self.prefetch_related("recovery")

    def unresolved(self) -> "InfractionQuerySet":
        """مخالفات لم تُغلق بعد (لا استرداد نقاط)."""
        return self.filter(recovery__isnull=True)

    # ── الإحصاء ───────────────────────────────────────────────────────────

    def summary_by_level(self):
        return self.values("level").annotate(count=Count("id")).order_by("level")

    def summary_by_category(self):
        return (
            self.values("violation_category__name_ar")
            .annotate(count=Count("id"))
            .order_by("-count")
        )


class RecoveryQuerySet(QuerySet):
    """QuerySet لـ BehaviorPointRecovery."""

    def approved(self) -> "RecoveryQuerySet":
        return self.filter(approved=True)

    def pending(self) -> "RecoveryQuerySet":
        return self.filter(approved=False)

    def for_student(self, student) -> "RecoveryQuerySet":
        return self.filter(infraction__student=student)

    def this_month(self) -> "RecoveryQuerySet":
        today = timezone.now().date()
        return self.filter(date__year=today.year, date__month=today.month)
