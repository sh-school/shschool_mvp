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


# ──────────────────── النطاق الزمنيّ: العام الدراسيّ ───────────────────────


class YearScopedQuerySet(models.QuerySet):
    """لكلّ نموذجٍ فيه `school` و`academic_year` و`is_active`.

    `is_active` تقول «هذا السجلُّ المعتمَد»، ولا تقول «هذا سجلُّ هذا العام».
    والعامُ يُشتقّ من تقويم الوزارة بتاريخه لا بزرٍّ يضغطه أحد، فسجلُّ العام
    الماضي يبقى نشطاً كما تُرك — وكلُّ استعلامٍ لا يُقيَّد بالعام يخلط العامين.

    وقد وقع هذا فعلاً في `ScheduleSlot`: بقيت مئتان وخمسون حصّةً من 2025-2026
    نشطةً بعد دخول 2026-2027، فكان المعلّمُ المتفرّغُ يُرى مشغولاً في اقتراح
    البدلاء، وشُعبةُ عامٍ مضى تدخل نطاقَ طلاب المنسّق فتتّسع صلاحيةُ قراءةٍ
    بلا قرار.

    فصار السؤالُ عن الحيّ يمرّ من هنا وحده: `Model.objects.live(school)`.
    """

    def of_year(self, school=None, *, year=None, on=None) -> YearScopedQuerySet:
        """سجلّاتُ عامٍ بعينه — الجاري افتراضاً — نشطةً كانت أو مطفأة."""
        qs = self if school is None else self.filter(school=school)
        return qs.filter(academic_year=year_or_current(school, year, on))

    def live(self, school=None, *, year=None, on=None) -> YearScopedQuerySet:
        """الحيّ: نشطُ العام الجاري وحدَه — وهذا ما تريده الشاشات كلُّها."""
        return self.of_year(school, year=year, on=on).filter(is_active=True)

    def past_years(self, school=None, *, year=None, on=None) -> YearScopedQuerySet:
        """سجلّاتُ الأعوام الأخرى — تُطفأ ولا تُعرض."""
        qs = self if school is None else self.filter(school=school)
        return qs.exclude(academic_year=year_or_current(school, year, on))


def year_or_current(school, year=None, on=None) -> str:
    """اسمُ العام المقصود: المُمرَّرُ صراحةً، وإلّا عامُ المدرسة من تقويم الوزارة.

    وبلا مدرسةٍ يُرتَدّ إلى العام الوطنيّ — فتقويم الوزارة واحدٌ لكلّ المدارس.
    """
    from core.academic_calendar import academic_year_for_school, default_academic_year

    if year is not None:
        return year
    if school is None:
        return default_academic_year()
    return academic_year_for_school(school, on)


# ─────────────────────────── CustomUser ────────────────────────────────────


class UserQuerySet(models.QuerySet):
    """QuerySet لـ CustomUser — يدعم البحث الذكي والفلترة الاحترافية."""

    # ── البحث ──────────────────────────────────────────────────────────────

    def search(self, query: str) -> UserQuerySet:
        """
        بحث Full-Text في الاسم الكامل والرقم الشخصي.
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

    # ── الانتماء إلى مدرسة ─────────────────────────────────────────────────

    def in_school(self, school) -> UserQuerySet:
        """من له عضويّةٌ فاعلةٌ في هذه المدرسة — مرّةً واحدةً مهما تعدّدت.

        و`filter(memberships__school=…)` ضمٌّ لا ترشيح: من له عضويّتان في
        المدرسة — معلّمٌ ومنسّقُ مادّةٍ مثلاً — يعود صفَّين. فيصحّ العدُّ
        خطأً، ويرفع `get()` استثناءَ «أكثرَ من واحد» على شخصٍ واحد.

        والترشيحُ باستعلامٍ داخليٍّ لا ضمّ: صفٌّ واحدٌ لكلّ إنسان، بلا
        `distinct()` تُخفي العلّةَ ولا تُزيلها.
        """
        from core.models import Membership

        return self.filter(
            id__in=Membership.objects.filter(school=school, is_active=True).values("user_id")
        )

    def ever_in_school(self, school) -> UserQuerySet:
        """من له عضويّةٌ في هذه المدرسة — قائمةً كانت أو منتهية.

        فمن نُقل هذا الصيفَ يبقى ملفُّه مقروءاً وجدولُ عامه الماضي منسوباً
        إليه. و`in_school` تسأل «أهو اليوم في الكادر؟»، وهذه تسأل «أكان منها
        يوماً؟» — سؤالان لا يُجاب عنهما بترشيحٍ واحد.
        """
        from core.models import Membership

        return self.filter(
            id__in=Membership.objects.filter(school=school).values("user_id")
        )

    # ── الفلترة حسب الدور ──────────────────────────────────────────────────

    def students(self, school=None) -> UserQuerySet:
        qs = self.filter(memberships__role__name="student")
        if school:
            qs = qs.filter(memberships__school=school)
        return qs.distinct()

    def teachers(self, school=None) -> UserQuerySet:
        """مَن يحمل نصاباً: الأدوارُ المدرِّسة بعضويّةٍ نشطة — لا دورُ `teacher` حرفيّاً."""
        from core.models.access import TEACHING_ROLES

        # الشروطُ في `filter()` واحدةٍ لتقع على العضويّة نفسها — لا عضويّةٍ
        # مدرِّسةٍ في مدرسةٍ وعضويّةٍ أخرى في هذه.
        membership = {"memberships__role__name__in": TEACHING_ROLES, "memberships__is_active": True}
        if school:
            membership["memberships__school"] = school
        return self.filter(**membership).distinct()

    def parents(self) -> UserQuerySet:
        return self.filter(memberships__role__name="parent").distinct()

    def staff(self, school=None) -> UserQuerySet:
        qs = self.filter(
            memberships__role__name__in=[
                "teacher",
                "principal",
                "vice_admin",
                "vice_academic",
                "coordinator",
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
        from core.models.access import TEACHING_ROLES

        # العضويّةُ النشطةُ شرطٌ هنا كما في `UserQuerySet.teachers()` — فمن غادر
        # لا يُعدّ مدرِّساً من أيّ باب.
        qs = self.filter(role__name__in=TEACHING_ROLES, is_active=True)
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
