"""
core/querysets.py — Custom QuerySets للنماذج الأساسية
======================================================
يوفّر طبقة query منفصلة قابلة للتسلسل (chainable) بدل تشتيت
المنطق في الـ views.
"""

from __future__ import annotations

import logging

from django.contrib.postgres.search import (
    SearchQuery,
    SearchRank,
    SearchVector,
    TrigramSimilarity,
)
from django.db import models
from django.db.models import Prefetch, Q
from django.utils import timezone

logger = logging.getLogger(__name__)


# ─────────────────────────── CustomUser ────────────────────────────────────


class UserQuerySet(models.QuerySet):
    """QuerySet لـ CustomUser — يدعم البحث الذكي والفلترة الاحترافية."""

    # ── البحث ──────────────────────────────────────────────────────────────

    def search(self, query: str) -> UserQuerySet:
        """
        بحث Full-Text في الاسم الكامل والرقم الوطني.
        يرتّب النتائج حسب الصلة (rank).
        """
        if not query:
            return self
        q = query.strip()[:100]
        vector = SearchVector("full_name", weight="A", config="arabic") + SearchVector(
            "national_id", weight="B"
        )
        search_query = SearchQuery(q, config="arabic", search_type="websearch")
        return (
            self.annotate(rank=SearchRank(vector, search_query))
            .filter(rank__gte=0.05)
            .order_by("-rank")
        )

    def search_fuzzy(self, query: str, threshold: float = 0.2) -> UserQuerySet:
        """
        بحث بالتشابه (Trigram) — يجد النتائج حتى مع أخطاء إملائية بسيطة.
        يتطلب تفعيل امتداد pg_trgm في قاعدة البيانات.
        """
        if not query:
            return self
        q = query.strip()[:100]
        return (
            self.annotate(
                sim_name=TrigramSimilarity("full_name", q),
                sim_national=TrigramSimilarity("national_id", q),
            )
            .filter(Q(sim_name__gte=threshold) | Q(sim_national__gte=threshold))
            .order_by("-sim_name")
        )

    def search_simple(self, query: str) -> UserQuerySet:
        """بحث بسيط بـ icontains — احتياطي إذا لم يكن pg_trgm مفعّلاً."""
        if not query:
            return self
        q = query.strip()[:100]
        return self.filter(Q(full_name__icontains=q) | Q(national_id__icontains=q))

    # ── الفلترة حسب الدور ──────────────────────────────────────────────────

    def students(self, school=None) -> UserQuerySet:
        qs = self.filter(memberships__role__name="student")
        if school:
            qs = qs.filter(memberships__school=school)
        return qs.distinct()

    def teachers(self, school=None) -> UserQuerySet:
        qs = self.filter(memberships__role__name="teacher")
        if school:
            qs = qs.filter(memberships__school=school)
        return qs.distinct()

    def parents(self) -> UserQuerySet:
        return self.filter(memberships__role__name="parent").distinct()

    def staff(self, school=None) -> UserQuerySet:
        qs = self.filter(
            memberships__role__name__in=[
                "teacher", "principal", "vice_admin", "vice_academic", "coordinator",
            ]
        )
        if school:
            qs = qs.filter(memberships__school=school)
        return qs.distinct()

    def active(self) -> UserQuerySet:
        return self.filter(is_active=True)

    def inactive(self) -> UserQuerySet:
        return self.filter(is_active=False)

    def locked(self) -> UserQuerySet:
        return self.filter(lockout_until__gt=timezone.now())

    # ── تحسين الـ queries (Prefetch) ───────────────────────────────────────

    def with_memberships(self) -> UserQuerySet:
        return self.prefetch_related("memberships", "memberships__role", "memberships__school")

    def with_profile(self) -> UserQuerySet:
        return self.select_related("profile")

    def with_enrollment(self) -> UserQuerySet:
        """يُحمّل الفصل الدراسي للطالب."""
        return self.prefetch_related(
            Prefetch(
                "studentenrollment_set",
                queryset=__import__(
                    "operations.models",
                    fromlist=["StudentEnrollment"],  # type: ignore[attr-defined]
                ).StudentEnrollment.objects.select_related("class_group"),
            )
        )

    # ── الفرز ──────────────────────────────────────────────────────────────

    def order_by_name(self) -> UserQuerySet:
        return self.order_by("full_name")

    def order_by_national_id(self) -> UserQuerySet:
        return self.order_by("national_id")


# ─────────────────────────── Membership ────────────────────────────────────


class MembershipQuerySet(models.QuerySet):
    def active(self) -> MembershipQuerySet:
        return self.filter(is_active=True)

    def for_school(self, school) -> MembershipQuerySet:
        return self.filter(school=school)

    def with_role(self, role_name: str) -> MembershipQuerySet:
        return self.filter(role__name=role_name)

    def students(self, school=None) -> MembershipQuerySet:
        qs = self.with_role("student")
        return qs.for_school(school) if school else qs

    def teachers(self, school=None) -> MembershipQuerySet:
        qs = self.with_role("teacher")
        return qs.for_school(school) if school else qs

    def with_user(self) -> MembershipQuerySet:
        return self.select_related("user", "role", "school")


# ─────────────────────────── AuditLog ──────────────────────────────────────


class AuditLogQuerySet(models.QuerySet):
    def for_user(self, user) -> AuditLogQuerySet:
        return self.filter(user=user)

    def for_school(self, school) -> AuditLogQuerySet:
        return self.filter(school=school)

    def action(self, action_type: str) -> AuditLogQuerySet:
        return self.filter(action=action_type)

    def recent(self, days: int = 30) -> AuditLogQuerySet:
        since = timezone.now() - timezone.timedelta(days=days)
        return self.filter(timestamp__gte=since)

    def sensitive(self) -> AuditLogQuerySet:
        """الإجراءات الحساسة التي تحتاج مراقبة."""
        return self.filter(
            action__in=["delete", "export", "decrypt", "login_failed", "permission_change"]
        )
