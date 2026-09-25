"""لجنة الجودة الموحَّدة (تنفيذيّةٌ ومراجعةٌ ذاتيّة) ومديرُها الذي يحصر الأعضاءَ النشطين."""

from django.db import models
from django.db.models import Q

from core.academic_calendar import academic_year_for_school, default_academic_year
from core.models import CustomUser, School

from .common import _uuid
from .operational import OperationalDomain

# ─────────────────────────────────────────────────────────────
# 3. اللجنة الموحّدة (تنفيذية + مراجعة ذاتية) — الإصلاح #2
# ─────────────────────────────────────────────────────────────


class CommitteeManager(models.Manager):
    """Manager يُوفّر استعلامات جاهزة على لجان الجودة"""

    def executor_committee(self, school, year=None):
        """أعضاء لجنة منفذي الخطة التشغيلية"""
        year = year or academic_year_for_school(school)
        return self.filter(
            school=school,
            academic_year=year,
            committee_type=QualityCommitteeMember.EXECUTOR,
            is_active=True,
        ).select_related("user", "domain")

    def review_committee(self, school, year=None):
        """أعضاء لجنة المراجعة الذاتية"""
        year = year or academic_year_for_school(school)
        return self.filter(
            school=school,
            academic_year=year,
            committee_type=QualityCommitteeMember.REVIEW,
            is_active=True,
        ).select_related("user", "domain")

    def search(self, school, year, name=None, role=None, domain=None, committee_type=None):
        """بحث متقدم عبر أعضاء اللجان"""
        qs = self.filter(school=school, academic_year=year, is_active=True)
        if name:
            qs = qs.filter(Q(user__full_name__icontains=name) | Q(job_title__icontains=name))
        if role:
            qs = qs.filter(responsibility=role)
        if domain:
            qs = qs.filter(domain=domain)
        if committee_type:
            qs = qs.filter(committee_type=committee_type)
        return qs.select_related("user", "domain")


class QualityCommitteeMember(models.Model):
    """
    عضو لجنة الجودة — يغطّي كلا اللجنتين:
      - EXECUTOR : لجنة منفذي الخطة التشغيلية
      - REVIEW   : لجنة المراجعة الذاتية

    الإصلاح #2: دمج OperationalPlanExecutorCommittee هنا مع إضافة:
      - committee_type  : نوع اللجنة
      - can_execute / can_review / can_report : صلاحيات على مستوى الفرد
    """

    # ── ثوابت نوع اللجنة ──
    EXECUTOR = "executor"
    REVIEW = "review"

    COMMITTEE_TYPE = [
        (EXECUTOR, "لجنة منفذي الخطة التشغيلية"),
        (REVIEW, "لجنة المراجعة الذاتية"),
    ]

    RESPONSIBILITY = [
        ("رئيس اللجنة", "رئيس اللجنة"),
        ("نائب رئيس اللجنة", "نائب رئيس اللجنة"),
        ("مقرر", "مقرر"),
        ("عضو", "عضو"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="quality_members", verbose_name="المدرسة"
    )
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="quality_memberships",
        null=True,
        blank=True,
        verbose_name="المستخدم",
    )
    job_title = models.CharField(max_length=100, verbose_name="المسمى الوظيفي")
    responsibility = models.CharField(
        max_length=30, choices=RESPONSIBILITY, verbose_name="المسؤولية"
    )
    committee_type = models.CharField(
        max_length=10,
        choices=COMMITTEE_TYPE,
        default=REVIEW,
        verbose_name="نوع اللجنة",
        db_index=True,
    )
    domain = models.ForeignKey(
        OperationalDomain,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="committee_members",
        verbose_name="المجال المسؤول عنه",
    )
    academic_year = models.CharField(
        max_length=9, default=default_academic_year, verbose_name="العام الدراسي"
    )
    is_active = models.BooleanField(default=True, verbose_name="نشط")

    # صلاحيات على مستوى الفرد (كانت على مستوى اللجنة كلها سابقاً)
    can_execute = models.BooleanField(default=True, verbose_name="صلاحية تنفيذ إجراء")
    can_review = models.BooleanField(default=True, verbose_name="صلاحية مراجعة إجراء")
    can_report = models.BooleanField(default=True, verbose_name="صلاحية رفع تقرير")

    objects = CommitteeManager()

    class Meta:
        verbose_name = "عضو لجنة جودة"
        verbose_name_plural = "أعضاء لجنة الجودة"
        ordering = ["committee_type", "responsibility", "job_title"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "academic_year", "user", "committee_type"],
                name="unique_member_per_committee_year",
            )
        ]

    def __str__(self):
        name = self.user.full_name if self.user else self.job_title
        committee_label = dict(self.COMMITTEE_TYPE).get(self.committee_type, "")
        return f"{name} — {self.responsibility} [{committee_label}]"

    def has_permission(self, perm: str) -> bool:
        """تحقق من صلاحية فردية"""
        return {
            "execute": self.can_execute,
            "review": self.can_review,
            "report": self.can_report,
        }.get(perm, False)

    @property
    def display_name(self) -> str:
        return self.user.full_name if self.user else self.job_title
