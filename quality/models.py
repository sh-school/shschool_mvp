"""
quality/models.py
الخطة التشغيلية + لجنة موحّدة (تنفيذية + مراجعة ذاتية) + ربط المنفذين
+ تقييم أداء الموظفين (متعدد المقيّمين + قوالب أدوار)
الهيكل الهرمي: مجال → هدف → مؤشر → إجراء → دليل

الإصلاحات:
- #2: دمج اللجان + CommitteeManager
- #5: نظام متعدد المقيّمين بأوزان (EvaluationScore)
- #6: قوالب تقييم مخصصة لكل دور (RoleEvaluationTemplate + EvaluationAxis)
- #7: توسيع _EVALUABLE_ROLES لتشمل كل الأدوار الوظيفية
"""

import uuid
from datetime import timedelta
from functools import cached_property

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.models import CustomUser, Membership, School


def _uuid():
    return uuid.uuid4()


# ── ثوابت وحدة الجودة ── Clean Code: G25 لا أرقام سحرية ──────
_DEFAULT_YEAR = settings.CURRENT_ACADEMIC_YEAR

# عتبات تقييم الأداء (القرار الأميري 9/2016)
_SCORE_EXCELLENT = 90
_SCORE_VERY_GOOD = 75
_SCORE_GOOD = 60

# الأدوار القابلة للتقييم — إصلاح #7: شاملة لكل الأدوار الوظيفية
_EVALUABLE_ROLES = frozenset(
    [
        "teacher",
        "ese_teacher",
        "coordinator",
        "social_worker",
        "psychologist",
        "academic_advisor",
        "specialist",
        "nurse",
        "librarian",
        "bus_supervisor",
        "admin_supervisor",
        "admin",
        "secretary",
        "it_technician",
        "vice_admin",
        "vice_academic",
    ]
)

# الأوزان الافتراضية للمحاور الأربعة (كل محور من 25)
_DEFAULT_AXES = [
    ("professional", "الكفاءة المهنية", 25),
    ("commitment", "الالتزام والمسؤولية", 25),
    ("teamwork", "العمل الجماعي والتواصل", 25),
    ("development", "التطوير المهني والمبادرة", 25),
]

# ─────────────────────────────────────────────────────────────
# 1. الهيكل الهرمي للخطة التشغيلية
# ─────────────────────────────────────────────────────────────


class OperationalDomain(models.Model):
    """المجال: التحصيل الأكاديمي / القيادة والإدارة / ..."""

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="op_domains")
    name = models.CharField(max_length=200, verbose_name="اسم المجال")
    academic_year = models.CharField(max_length=9, default=settings.CURRENT_ACADEMIC_YEAR)
    order = models.IntegerField(default=0)

    # ربط QuerySet الموجود
    from quality.querysets import DomainQuerySet

    objects = DomainQuerySet.as_manager()

    class Meta:
        verbose_name = "مجال"
        verbose_name_plural = "المجالات"
        ordering = ["order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "name", "academic_year"],
                name="unique_domain_per_year",
            )
        ]

    def __str__(self):
        return self.name

    @property
    def total_procedures(self):
        """عدد الإجراءات — يُفضّل استخدام DomainQuerySet.with_progress() لتجنب N+1"""
        # إذا كانت القيمة مُحسَّبة عبر annotate، استخدمها مباشرة
        if hasattr(self, "_total_procedures_cache"):
            return self._total_procedures_cache
        return OperationalProcedure.objects.filter(indicator__target__domain=self).count()

    @total_procedures.setter
    def total_procedures(self, value):
        self._total_procedures_cache = value

    @property
    def completed_procedures(self):
        if hasattr(self, "_completed_procedures_cache"):
            return self._completed_procedures_cache
        return OperationalProcedure.objects.filter(
            indicator__target__domain=self, status="Completed"
        ).count()

    @completed_procedures.setter
    def completed_procedures(self, value):
        self._completed_procedures_cache = value

    @property
    def completion_pct(self):
        total = self.total_procedures
        return round(self.completed_procedures / total * 100) if total else 0


class OperationalTarget(models.Model):
    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    domain = models.ForeignKey(OperationalDomain, on_delete=models.CASCADE, related_name="targets")
    number = models.CharField(max_length=20, verbose_name="رقم الهدف")
    text = models.TextField(verbose_name="نص الهدف")

    class Meta:
        verbose_name = "هدف"
        verbose_name_plural = "الأهداف"
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["domain", "number"], name="unique_target_in_domain")
        ]

    def __str__(self):
        return f"[{self.number}] {self.text[:60]}"


class OperationalIndicator(models.Model):
    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    target = models.ForeignKey(
        OperationalTarget, on_delete=models.CASCADE, related_name="indicators"
    )
    number = models.CharField(max_length=30, verbose_name="رقم المؤشر")
    text = models.TextField(verbose_name="نص المؤشر")

    class Meta:
        verbose_name = "مؤشر"
        verbose_name_plural = "المؤشرات"
        ordering = ["number"]

    def __str__(self):
        return f"[{self.number}] {self.text[:60]}"


class OperationalProcedure(models.Model):
    STATUS = [
        ("Not Started", "لم يبدأ"),
        ("In Progress", "قيد التنفيذ"),
        ("Pending Review", "بانتظار المراجعة"),
        ("Completed", "مكتمل"),
        ("Cancelled", "ملغى"),
    ]
    EVIDENCE_TYPE = [
        ("وصفي", "وصفي"),
        ("كمي", "كمي"),
        ("كمي/وصفي", "كمي/وصفي"),
        ("", "—"),
    ]
    EVIDENCE_REQUEST_STATUS = [
        ("not_requested", "غير مطلوب"),
        ("requested", "مطلوب"),
        ("submitted", "تم الرفع"),
    ]
    QUALITY_RATING = [
        ("", "بدون تقييم"),
        ("متحقق", "متحقق"),
        ("متحقق جزئيا", "متحقق جزئياً"),
        ("غير متحقق", "غير متحقق"),
    ]
    FOLLOW_UP_CHOICES = [
        ("", "—"),
        ("تم الإنجاز", "تم الإنجاز"),
        ("قيد الإنجاز", "قيد الإنجاز"),
        ("لم يتم الإنجاز", "لم يتم الإنجاز"),
        ("مؤجل", "مؤجل"),
        ("بانتظار المراجعة", "بانتظار المراجعة"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    indicator = models.ForeignKey(
        OperationalIndicator, on_delete=models.CASCADE, related_name="procedures"
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="procedures")
    number = models.CharField(max_length=30, verbose_name="رقم الإجراء", db_index=True)
    text = models.TextField(verbose_name="نص الإجراء")

    # المنفذ — نص موحَّد + مستخدم مربوط
    executor_norm = models.CharField(max_length=100, verbose_name="المنفذ (نص)", db_index=True)
    executor_user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_procedures",
        verbose_name="المنفذ (مستخدم)",
    )

    date_range = models.CharField(max_length=50, verbose_name="الفترة الزمنية", blank=True)
    deadline = models.DateField(null=True, blank=True, verbose_name="الموعد النهائي")
    status = models.CharField(max_length=20, choices=STATUS, default="In Progress", db_index=True)
    evaluation = models.TextField(blank=True, verbose_name="التقييم")
    evaluation_notes = models.TextField(blank=True, verbose_name="ملاحظات التقييم")
    follow_up = models.TextField(blank=True, verbose_name="المتابعة")
    comments = models.TextField(blank=True, verbose_name="تعليقات")
    evidence_type = models.CharField(max_length=20, choices=EVIDENCE_TYPE, blank=True)
    evidence_source_employee = models.TextField(blank=True, verbose_name="موظف مصدر الدليل")
    evidence_source_file = models.TextField(blank=True, verbose_name="ملف مصدر الدليل")

    # طلب الدليل من لجنة المراجعة (جديد)
    evidence_request_status = models.CharField(
        max_length=20,
        choices=EVIDENCE_REQUEST_STATUS,
        default="not_requested",
        verbose_name="حالة طلب الدليل",
    )
    evidence_request_note = models.TextField(blank=True, verbose_name="ملاحظات طلب الدليل")

    # التقييم النوعي من لجنة المراجعة (جديد)
    quality_rating = models.CharField(
        max_length=20,
        choices=QUALITY_RATING,
        default="",
        blank=True,
        verbose_name="التقييم النوعي للأداء",
    )

    # حقول المراجعة (Approval Workflow)
    reviewed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_procedures",
        verbose_name="المراجع",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ المراجعة")
    review_note = models.TextField(blank=True, verbose_name="ملاحظة المراجعة")

    academic_year = models.CharField(max_length=9, default=settings.CURRENT_ACADEMIC_YEAR)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ربط QuerySet الموجود
    from quality.querysets import ProcedureQuerySet

    objects = ProcedureQuerySet.as_manager()

    class Meta:
        verbose_name = "إجراء"
        verbose_name_plural = "الإجراءات"
        ordering = ["number"]
        indexes = [
            models.Index(fields=["school", "status"]),
            models.Index(fields=["executor_norm"]),
            models.Index(fields=["school", "academic_year"]),
            models.Index(fields=["deadline"]),
        ]

    def __str__(self):
        return f"[{self.number}] {self.text[:60]}"

    # ── Properties للمواعيد ───────────────────────────────────────

    @property
    def is_overdue(self):
        """هل تجاوز الإجراء الموعد النهائي؟"""
        if not self.deadline or self.status in ("Completed", "Cancelled"):
            return False
        return self.deadline < timezone.now().date()

    @property
    def is_due_soon(self):
        """هل الإجراء قريب من الموعد النهائي (7 أيام)؟"""
        if not self.deadline or self.status in ("Completed", "Cancelled"):
            return False
        today = timezone.now().date()
        return today <= self.deadline <= today + timedelta(days=7)

    @property
    def is_due_urgent(self):
        """هل الإجراء عاجل (3 أيام أو أقل)؟"""
        if not self.deadline or self.status in ("Completed", "Cancelled"):
            return False
        today = timezone.now().date()
        return today <= self.deadline <= today + timedelta(days=3)

    @property
    def days_overdue(self):
        """عدد أيام التأخير عن الموعد النهائي."""
        if not self.deadline or self.status in ("Completed", "Cancelled"):
            return 0
        today = timezone.now().date()
        diff = (today - self.deadline).days
        return max(diff, 0)

    @property
    def committee_decision_display(self):
        """عرض قرار اللجنة كنص مقروء."""
        if self.status == "Completed" and self.reviewed_by:
            return "معتمد"
        if self.status == "In Progress" and self.reviewed_by:
            return "مُعاد للمنفذ"
        if self.status == "Pending Review":
            return "بانتظار القرار"
        if self.status == "Cancelled":
            return "ملغى"
        return "بدون قرار"

    @property
    def follow_up_display(self):
        """عرض حالة المتابعة."""
        return self.follow_up or "لم يتم الإنجاز"


class ProcedureEvidence(models.Model):
    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    procedure = models.ForeignKey(
        OperationalProcedure, on_delete=models.CASCADE, related_name="evidences"
    )
    uploaded_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, related_name="uploaded_evidences"
    )
    title = models.CharField(max_length=200, verbose_name="عنوان الدليل")
    description = models.TextField(blank=True)
    file = models.FileField(upload_to="evidence/%Y/%m/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "دليل"
        verbose_name_plural = "الأدلة"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} — {self.procedure.number}"


# ─────────────────────────────────────────────────────────────
# 1b. سجل تغييرات الحالة (Timeline)
# ─────────────────────────────────────────────────────────────


class ProcedureStatusLog(models.Model):
    """سجل كل تغيير حالة على الإجراء — يُعرض كـ timeline."""

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    procedure = models.ForeignKey(
        OperationalProcedure,
        on_delete=models.CASCADE,
        related_name="status_logs",
    )
    old_status = models.CharField(max_length=20, verbose_name="الحالة السابقة")
    new_status = models.CharField(max_length=20, verbose_name="الحالة الجديدة")
    changed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="procedure_status_changes",
    )
    note = models.TextField(blank=True, verbose_name="ملاحظة")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "سجل تغيير حالة"
        verbose_name_plural = "سجل تغييرات الحالة"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.procedure.number}: {self.old_status} → {self.new_status}"


# ─────────────────────────────────────────────────────────────
# 2. ربط المنفذين بالمستخدمين
# ─────────────────────────────────────────────────────────────


class ExecutorMapping(models.Model):
    """
    ربط المسمى الوظيفي (executor_norm) بمستخدم حقيقي.
    بعد الربط، تُحدَّث executor_user في كل الإجراءات المرتبطة
    بهذا المسمى تلقائياً عبر apply_mapping().
    """

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="executor_mappings")
    executor_norm = models.CharField(max_length=100, verbose_name="المسمى الوظيفي", db_index=True)
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="executor_mappings",
        verbose_name="الموظف",
    )
    academic_year = models.CharField(max_length=9, default=settings.CURRENT_ACADEMIC_YEAR)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "ربط منفذ"
        verbose_name_plural = "ربط المنفذين"
        ordering = ["executor_norm"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "executor_norm", "academic_year"],
                name="unique_executor_mapping_per_school_year",
            )
        ]

    def __str__(self):
        user_name = self.user.full_name if self.user else "غير مربوط"
        return f"{self.executor_norm} → {user_name}"

    def apply_mapping(self):
        """
        تُحدِّث executor_user في كل الإجراءات التي تحمل هذا executor_norm
        في نفس المدرسة والعام الدراسي.
        """
        OperationalProcedure.objects.filter(
            school=self.school,
            academic_year=self.academic_year,
            executor_norm=self.executor_norm,
        ).update(executor_user=self.user)


# ─────────────────────────────────────────────────────────────
# 3. اللجنة الموحّدة (تنفيذية + مراجعة ذاتية) — الإصلاح #2
# ─────────────────────────────────────────────────────────────


class CommitteeManager(models.Manager):
    """Manager يُوفّر استعلامات جاهزة على لجان الجودة"""

    def executor_committee(self, school, year=_DEFAULT_YEAR):
        """أعضاء لجنة منفذي الخطة التشغيلية"""
        return self.filter(
            school=school,
            academic_year=year,
            committee_type=QualityCommitteeMember.EXECUTOR,
            is_active=True,
        ).select_related("user", "domain")

    def review_committee(self, school, year=_DEFAULT_YEAR):
        """أعضاء لجنة المراجعة الذاتية"""
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
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="quality_members")
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="quality_memberships",
        null=True,
        blank=True,
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
    academic_year = models.CharField(max_length=9, default=settings.CURRENT_ACADEMIC_YEAR)
    is_active = models.BooleanField(default=True)

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


# ─────────────────────────────────────────────────────────────
# Phase 6 — تقييم أداء الموظفين
# القرار الأميري 9/2016 م.11 + قانون تنظيم المدارس 9/2017
# إصلاح #5: متعدد المقيّمين | #6: قوالب أدوار | #3: تحسين الأداء
# ─────────────────────────────────────────────────────────────


class RoleEvaluationTemplate(models.Model):
    """
    إصلاح #6 — قالب تقييم مخصص لكل دور وظيفي.
    يحدد محاور التقييم وأوزانها لكل دور.
    مثال: المعلم → 4 محاور بأوزان مختلفة عن الممرض.
    إذا لم يوجد قالب للدور، تُستخدم المحاور الافتراضية (4×25).
    """

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="eval_templates"
    )
    role_name = models.CharField(
        max_length=30, verbose_name="الدور الوظيفي",
        help_text="يطابق Role.name — مثل teacher, nurse, librarian",
    )
    academic_year = models.CharField(max_length=9, default=settings.CURRENT_ACADEMIC_YEAR)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "قالب تقييم دور"
        verbose_name_plural = "قوالب تقييم الأدوار"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "role_name", "academic_year"],
                name="unique_eval_template_per_role_year",
            )
        ]

    def __str__(self):
        return f"قالب {self.role_name} — {self.academic_year}"

    @property
    def total_weight(self):
        return sum(a.weight for a in self.axes.all())


class EvaluationAxis(models.Model):
    """
    محور تقييم ضمن قالب دور — إصلاح #6.
    يسمح بتعريف محاور مخصصة لكل دور بأوزان مختلفة.
    """

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    template = models.ForeignKey(
        RoleEvaluationTemplate, on_delete=models.CASCADE, related_name="axes"
    )
    key = models.CharField(
        max_length=50, verbose_name="معرّف المحور",
        help_text="معرّف برمجي — مثل professional, commitment, teaching_skills",
    )
    label = models.CharField(max_length=200, verbose_name="اسم المحور")
    weight = models.PositiveSmallIntegerField(
        default=25, verbose_name="الوزن (من 100)"
    )
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "محور تقييم"
        verbose_name_plural = "محاور التقييم"
        ordering = ["order", "key"]
        constraints = [
            models.UniqueConstraint(
                fields=["template", "key"],
                name="unique_axis_per_template",
            )
        ]

    def __str__(self):
        return f"{self.label} ({self.weight})"


class EmployeeEvaluation(models.Model):
    PERIODS = [
        ("S1", "نهاية الفصل الأول"),
        ("S2", "نهاية العام الدراسي"),
    ]
    RATINGS = [
        ("excellent", "ممتاز (90–100)"),
        ("very_good", "جيد جداً (75–89)"),
        ("good", "جيد (60–74)"),
        ("needs_dev", "يحتاج تطوير (أقل من 60)"),
    ]
    STATUS = [
        ("draft", "مسودة"),
        ("submitted", "مُقدَّم"),
        ("approved", "مُعتمد"),
        ("acknowledged", "مُستلم من الموظف"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="evaluations")
    employee = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="evaluations", verbose_name="الموظف"
    )
    evaluator = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="evaluations_given",
        verbose_name="المقيِّم الرئيسي",
    )
    template = models.ForeignKey(
        RoleEvaluationTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evaluations",
        verbose_name="قالب التقييم",
        help_text="يُحدَّد تلقائياً حسب دور الموظف. null = المحاور الافتراضية",
    )
    academic_year = models.CharField(max_length=9, default=settings.CURRENT_ACADEMIC_YEAR)
    period = models.CharField(max_length=2, choices=PERIODS, verbose_name="الفترة")
    status = models.CharField(max_length=15, choices=STATUS, default="draft")

    # المحاور الأربعة الافتراضية (backward compatible)
    axis_professional = models.PositiveSmallIntegerField(
        default=0, verbose_name="الكفاءة المهنية (25)"
    )
    axis_commitment = models.PositiveSmallIntegerField(
        default=0, verbose_name="الالتزام والمسؤولية (25)"
    )
    axis_teamwork = models.PositiveSmallIntegerField(
        default=0, verbose_name="العمل الجماعي والتواصل (25)"
    )
    axis_development = models.PositiveSmallIntegerField(
        default=0, verbose_name="التطوير المهني والمبادرة (25)"
    )
    total_score = models.PositiveSmallIntegerField(default=0, verbose_name="المجموع الكلي")
    rating = models.CharField(max_length=15, choices=RATINGS, blank=True)
    strengths = models.TextField(blank=True, verbose_name="نقاط القوة")
    improvements = models.TextField(blank=True, verbose_name="مجالات التطوير")
    goals_next = models.TextField(blank=True, verbose_name="أهداف الفترة القادمة")
    employee_comment = models.TextField(blank=True, verbose_name="تعليق الموظف")
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "تقييم موظف"
        verbose_name_plural = "تقييمات الموظفين"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "employee", "academic_year", "period"],
                name="unique_eval_per_period",
            )
        ]

    def __str__(self):
        return f"{self.employee.full_name} | {self.get_period_display()} | {self.academic_year}"

    # ── الحقول التي تستوجب إعادة حساب المجموع ──
    _AXIS_FIELDS = frozenset([
        "axis_professional", "axis_commitment",
        "axis_teamwork", "axis_development",
    ])

    def calculate_total(self):
        """حساب المجموع من المحاور الأربعة الافتراضية + التقدير"""
        self.total_score = (
            self.axis_professional
            + self.axis_commitment
            + self.axis_teamwork
            + self.axis_development
        )
        if self.total_score >= _SCORE_EXCELLENT:
            self.rating = "excellent"
        elif self.total_score >= _SCORE_VERY_GOOD:
            self.rating = "very_good"
        elif self.total_score >= _SCORE_GOOD:
            self.rating = "good"
        else:
            self.rating = "needs_dev"

    def calculate_weighted_total(self):
        """
        إصلاح #5 — حساب المجموع المرجح من EvaluationScore (متعدد المقيّمين).
        إذا وُجدت تقييمات فردية، يُحسب المتوسط المرجح.
        وإلا يُستخدم المحاور الأربعة الافتراضية.
        """
        scores = self.scores.all()
        if not scores.exists():
            self.calculate_total()
            return

        weighted_sum = 0
        total_weight = 0
        for score in scores:
            weighted_sum += score.total_score * score.weight
            total_weight += score.weight

        if total_weight > 0:
            self.total_score = round(weighted_sum / total_weight)
        else:
            self.calculate_total()
            return

        if self.total_score >= _SCORE_EXCELLENT:
            self.rating = "excellent"
        elif self.total_score >= _SCORE_VERY_GOOD:
            self.rating = "very_good"
        elif self.total_score >= _SCORE_GOOD:
            self.rating = "good"
        else:
            self.rating = "needs_dev"

    def save(self, *args, **kwargs):
        # إصلاح #3: حساب المجموع فقط عندما لا يكون update_fields محدداً
        # أو عندما تتضمن update_fields أحد حقول المحاور
        update_fields = kwargs.get("update_fields")
        if update_fields is None or self._AXIS_FIELDS & set(update_fields):
            self.calculate_total()
            # إضافة total_score و rating لقائمة update_fields إذا كانت محددة
            if update_fields is not None:
                update_fields = list(update_fields)
                for f in ("total_score", "rating"):
                    if f not in update_fields:
                        update_fields.append(f)
                kwargs["update_fields"] = update_fields
        super().save(*args, **kwargs)

    def acknowledge(self):
        self.status = "acknowledged"
        self.acknowledged_at = timezone.now()
        self.save(update_fields=["status", "acknowledged_at"])

    def recalculate_from_scores(self):
        """أعد حساب المجموع من تقييمات المقيّمين المتعددين"""
        self.calculate_weighted_total()
        self.save(update_fields=["total_score", "rating"])


class EvaluationScore(models.Model):
    """
    إصلاح #5 — تقييم فردي من مقيِّم واحد ضمن تقييم متعدد المقيّمين.
    المعلم مثلاً: مدير (40%) + نائب أكاديمي (35%) + منسق (25%)

    كل مقيِّم يعطي درجات على المحاور الأربعة الافتراضية،
    أو على محاور القالب المخصص عبر JSON.
    """

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    evaluation = models.ForeignKey(
        EmployeeEvaluation, on_delete=models.CASCADE, related_name="scores"
    )
    evaluator = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="evaluation_scores_given",
        verbose_name="المقيِّم",
    )
    weight = models.PositiveSmallIntegerField(
        default=100, verbose_name="الوزن (%)",
        help_text="وزن هذا المقيِّم — مثل 40 للمدير، 35 للنائب، 25 للمنسق",
    )

    # المحاور الافتراضية
    axis_professional = models.PositiveSmallIntegerField(default=0)
    axis_commitment = models.PositiveSmallIntegerField(default=0)
    axis_teamwork = models.PositiveSmallIntegerField(default=0)
    axis_development = models.PositiveSmallIntegerField(default=0)
    total_score = models.PositiveSmallIntegerField(default=0)

    # محاور مخصصة (JSON) — للقوالب المخصصة
    custom_axes = models.JSONField(
        default=dict, blank=True,
        verbose_name="محاور مخصصة",
        help_text='{"teaching_skills": 20, "classroom_mgmt": 22, ...}',
    )

    note = models.TextField(blank=True, verbose_name="ملاحظات المقيِّم")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "تقييم مقيِّم"
        verbose_name_plural = "تقييمات المقيِّمين"
        ordering = ["-weight"]
        constraints = [
            models.UniqueConstraint(
                fields=["evaluation", "evaluator"],
                name="unique_score_per_evaluator",
            )
        ]

    def __str__(self):
        return (
            f"{self.evaluator.full_name} → "
            f"{self.evaluation.employee.full_name} ({self.weight}%)"
        )

    def calculate_total(self):
        """حساب مجموع المحاور"""
        if self.custom_axes:
            self.total_score = sum(self.custom_axes.values())
        else:
            self.total_score = (
                self.axis_professional
                + self.axis_commitment
                + self.axis_teamwork
                + self.axis_development
            )

    def save(self, *args, **kwargs):
        self.calculate_total()
        super().save(*args, **kwargs)


class EvaluationCycle(models.Model):
    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="eval_cycles")
    academic_year = models.CharField(max_length=9, default=settings.CURRENT_ACADEMIC_YEAR)
    period = models.CharField(max_length=2, choices=EmployeeEvaluation.PERIODS)
    deadline = models.DateField(verbose_name="الموعد النهائي للتقييم")
    is_closed = models.BooleanField(default=False)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "دورة تقييم"
        verbose_name_plural = "دورات التقييم"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "academic_year", "period"],
                name="unique_eval_cycle",
            )
        ]

    def __str__(self):
        return f"{self.school.code} | {self.get_period_display()} | {self.academic_year}"

    # إصلاح #4: cached_property لتجنب 2×N queries
    @cached_property
    def completion_rate(self):
        total_staff = Membership.objects.filter(
            school=self.school,
            is_active=True,
            role__name__in=_EVALUABLE_ROLES,
        ).count()
        evaluated = EmployeeEvaluation.objects.filter(
            school=self.school,
            academic_year=self.academic_year,
            period=self.period,
            status__in=["submitted", "approved", "acknowledged"],
        ).count()
        return round(evaluated / total_staff * 100) if total_staff else 0
