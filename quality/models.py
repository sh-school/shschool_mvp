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

import math
import uuid
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction
from functools import cached_property
from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.academic_calendar import academic_year_for_school, default_academic_year
from core.models import CustomUser, Membership, School

from .appraisal_forms import forms_by_role


def _uuid():
    return uuid.uuid4()


# ── ثوابت وحدة الجودة ── Clean Code: G25 لا أرقام سحرية ──────
# عتباتُ مستويات تقييم الأداء — المادة 16 من النظام الوظيفي لموظفي المدارس
# (قرار مجلس الوزراء 32/2019)، «02- النظام الوظيفي لموظفي المدارس.pdf» صفحتا
# الملفّ 10–11 (المطبوعتان 24–25)، ونقلُها في 02_staff_affairs.md:201-205:
#   ممتاز «(90%) فأعلى» · جيد جداً «أعلى من (75%) إلى أقل من (90%)»
#   جيد «أعلى من (65%) إلى (75%)» · مقبول «من (50%) إلى (65%)» · ضعيف «أقل من (50%)»
# فالحدودُ مغلقةٌ عند 90 و50 ومفتوحةٌ عند 75 و65. ومفتاحُ الاستمارات السبع
# (06_attendance_performance_review.md §2.2: 100–90 / 89–76 / 75–66 / 65–50 / أقل من 50)
# يطابقها في الأعداد الصحيحة. وكان التعليقُ هنا يُسند 90/75/60 إلى «القرار الأميري
# 9/2016» ولا أثرَ له في المصدر.
_SCORE_EXCELLENT = 90  # ممتاز: s >= 90
_SCORE_VERY_GOOD_ABOVE = 75  # جيد جداً: 75 < s < 90
_SCORE_GOOD_ABOVE = 65  # جيد: 65 < s <= 75
_SCORE_ACCEPTABLE = 50  # مقبول: 50 <= s <= 65؛ وما دونه ضعيف

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
        # مسؤولُ النقل: تكليفٌ على «مشرف إداري» (الإداريّة 1) — «المشرف الإداري (مسؤول
        # الحافلات)» في «الدليل التنظيمي لسياسة إدارة سلوك الطلبة 2026.pdf» صفحة الملفّ 105.
        "transport_officer",
        "admin_supervisor",
        "admin",
        "secretary",
        "it_technician",
        "vice_admin",
        "vice_academic",
        # أدوارٌ تسمّيها الاستماراتُ الوزاريّة نصّاً (06_attendance_performance_review.md
        # §2.3، §2.7–2.9) — بذرُ قوالبها بلا ظهورها في قائمة التقييم بذرٌ لا يُقرأ.
        "student_observer",
        "services_worker",
        "support_companion",
        "messenger",
        "storekeeper",
        "canteen_supervisor",
        "accountant",
        "receptionist",
        "e_projects_coordinator",
        "lab_technician",
        "teacher_assistant",
        "ese_assistant",
        # «اخصائي أنشطة مدرسية» خانةٌ في رأس «استمارة تقييم الوظائف الادارية 3.pdf» ص1،
        # والمسمّى الوزاريّ للدور «أخصائي الأنشطة»: «06- ضوابط البرامج والأنشطة.pdf» ص3
        # (صلاحيةُ النظام «بالنائب الأكاديمي وأخصائي الأنشطة») وص12 (يُقيَّم «من خلال
        # استمارات التقييم والمتابعة»). ولفظُ «منسق الأنشطة» لا يرد في أيّ PDF.
        "activities_coordinator",
    ]
)

# ── التظلّم من تقرير تقييم الأداء — المادة 20 ─────────────────────────────
# «02- النظام الوظيفي لموظفي المدارس.pdf» صفحتا الملفّ 12–13 (المطبوعتان 26–27)، ونقلُها
# في 02_staff_affairs.md:211 — بنصّها كاملاً من الصورة:
# «يُعلن الموظف بنسخة من تقرير تقييم الأداء، ويجوز للموظف أن يتظلم منه إلى لجنة موظفي
# المدارس، خلال خمسة عشر يوماً من تاريخ علمه، وتبت اللجنة في التظلم خلال ثلاثين يوماً من
# تاريخ تقديمه، ويعتبر انقضاء الميعاد المذكور دون إخطار الموظف بتعديل التقرير بمثابة قرار
# بالرفض، ويكون قرار اللجنة في التظلم نهائياً بعد اعتماده من الوزير، ولا يعتبر التقرير
# نهائياً إلا بعد انقضاء ميعاد التظلم منه أو البت فيه».
# والنصُّ لا يقول أهي أيّامٌ تقويميّةٌ أم أيّامُ عمل — فالمهلتان ونوعُ الأيّام إعدادات.
APPRAISAL_GRIEVANCE_WINDOW_DAYS = 15
APPRAISAL_GRIEVANCE_DECISION_DAYS = 30


def _grievance_days(name: str, default: int) -> timedelta:
    kind = getattr(settings, "APPRAISAL_GRIEVANCE_DAY_KIND", "calendar")
    if kind != "calendar":
        # أيّامُ العمل تحتاج تقويمَ العطل الرسميّة؛ ولا يُخمَّن — المصدرُ صامتٌ عن النوع.
        raise ImproperlyConfigured(
            "APPRAISAL_GRIEVANCE_DAY_KIND: المدعومُ «calendar» وحده حتى يُقرَّر نوعُ الأيّام"
        )
    return timedelta(days=int(getattr(settings, name, default)))


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
    academic_year = models.CharField(max_length=9, default=default_academic_year)
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

    academic_year = models.CharField(max_length=9, default=default_academic_year)
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
    academic_year = models.CharField(max_length=9, default=default_academic_year)
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
    academic_year = models.CharField(max_length=9, default=default_academic_year)
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
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="eval_templates")
    role_name = models.CharField(
        max_length=30,
        verbose_name="الدور الوظيفي",
        help_text="يطابق Role.name — مثل teacher, nurse, librarian",
    )
    academic_year = models.CharField(max_length=9, default=default_academic_year)
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

    def matches_ministry_form(self) -> bool:
        """
        أهو استمارةُ دوره كما طُبعت؟ الدورُ في `forms_by_role()`، ومحاورُه بمفاتيحها وأوزانها
        محاورُ تلك الاستمارة لا غير (`quality/ministry_appraisal_forms.json`، المنسوخ من
        06_attendance_performance_review.md §2.3–2.9). فالتقريرُ السنويّ «وفقاً للنماذج المعتمدة
        من الوزير» (المادة 15، 02_staff_affairs.md:199)، وقالبٌ لدورٍ بلا استمارة أو بوزنٍ
        غُيِّر بعد البذر ليس منها. (يقرأ `.all()` ليكفيه `prefetch_related("axes")`.)
        """
        form = forms_by_role().get(self.role_name)
        if form is None:
            return False
        printed = {(axis.key, axis.weight) for axis in form.axes}
        stored = [(axis.key, axis.weight) for axis in self.axes.all()]
        return len(stored) == len(printed) and set(stored) == printed


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
        max_length=50,
        verbose_name="معرّف المحور",
        help_text="معرّف برمجي — مثل professional, commitment, teaching_skills",
    )
    label = models.CharField(max_length=200, verbose_name="اسم المحور")
    weight = models.PositiveSmallIntegerField(default=25, verbose_name="الوزن (من 100)")
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
    #: التقريرُ الوزاريّ سنويٌّ واحد: «تضع المدرسة تقارير تقييم أداء الموظفين سنوياً»
    #: (02_staff_affairs.md:199)، و«سنوية في كل الاستمارات السبع» (06:99). فـS2 هو
    #: التقرير، وS1 متابعةٌ داخليّةٌ لا سندَ وزاريَّ لها — تبقى ببياناتها، ومصيرُها للمالك
    #: (ADR-0002 §6.6).
    PERIODS = [
        ("S1", "متابعة منتصف العام (داخليّة، غير وزاريّة)"),
        ("S2", "التقرير السنويّ (الوزاريّ)"),
    ]
    MINISTRY_PERIOD = "S2"
    #: مستوياتُ المادة 16 الخمسة بأسمائها، والنطاقُ بمفتاح الاستمارات (06 §2.2).
    RATINGS = [
        ("excellent", "ممتاز (100–90)"),
        ("very_good", "جيد جداً (89–76)"),
        ("good", "جيد (75–66)"),
        ("acceptable", "مقبول (65–50)"),
        ("weak", "ضعيف (أقل من 50)"),
    ]
    #: قرارُ لجنة موظفي المدارس في التظلّم (المادة 20): «بتعديل التقرير»، أو الرفضُ.
    GRIEVANCE_OUTCOMES = [
        ("rejected", "رفضُ التظلّم"),
        ("modified", "تعديلُ التقرير"),
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
    # RESTRICT لا SET_NULL: فكُّ الربط بحذف القالب كان يُسقط درجاتِ `custom_axes` من المجموع
    # (فيُحسب من المحاور الافتراضيّة الصفريّة). ويبقى حذفُ المدرسة كلِّها متتالياً.
    template = models.ForeignKey(
        RoleEvaluationTemplate,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="evaluations",
        verbose_name="قالب التقييم",
        help_text="يُحدَّد تلقائياً حسب دور الموظف. null = المحاور الافتراضية",
    )
    academic_year = models.CharField(max_length=9, default=default_academic_year)
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
    #: «تاريخ علمه» (المادة 20) — ومنه تبدأ مهلةُ التظلّم.
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    #: لحظةُ اعتماد المدير («ويعتمد من مدير المدرسة» — المادة 16). ولا يُعلم الموظّفُ
    #: بتقريرٍ قبل اعتماده، فهي الحدُّ الأدنى لتاريخ الاستلام المدوَّن (المادة 20).
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ اعتماد المدير")
    grievance_submitted_on = models.DateField(
        null=True, blank=True, verbose_name="تاريخ تقديم التظلّم إلى لجنة موظفي المدارس"
    )
    grievance_decided_on = models.DateField(
        null=True, blank=True, verbose_name="تاريخ إخطار الموظّف بقرار اللجنة"
    )
    #: سببُ التظلّم بقلم الموظّف — يُحال إلى لجنة موظفي المدارس مع التقرير.
    grievance_reason = models.TextField(blank=True, db_default="", verbose_name="سبب التظلّم")
    grievance_outcome = models.CharField(
        max_length=10,
        choices=GRIEVANCE_OUTCOMES,
        blank=True,
        db_default="",
        verbose_name="قرار اللجنة في التظلّم",
    )
    #: «ويكون قرار اللجنة في التظلم نهائياً بعد اعتماده من الوزير» (المادة 20، صفحة الملفّ 13).
    grievance_decision_approved_on = models.DateField(
        null=True, blank=True, verbose_name="تاريخ اعتماد الوزير لقرار اللجنة في التظلّم"
    )
    #: «تاريخ استلام الموظف (يرجى تدوين التاريخ في حالة رفض الموظف التوقيع)» — «استمارة
    #: تقييم المعلم والدليل التفسيري.pdf» ص2. يدوّنه المدير فيكون «تاريخ علمه» (المادة 20).
    received_on = models.DateField(
        null=True, blank=True, verbose_name="تاريخ استلام الموظف (عند رفضه التوقيع)"
    )
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
    _AXIS_FIELDS = frozenset(
        [
            "axis_professional",
            "axis_commitment",
            "axis_teamwork",
            "axis_development",
        ]
    )

    @staticmethod
    def rating_for(total: int | Decimal | Fraction) -> str:
        """
        المستوى من المجموع بحدود المادة 16 كما صيغت (ثوابت أعلى الوحدة).

        يقبل الكسرَ عمداً: المادةُ تصوغ الحدودَ متّصلةً («أعلى من 75»، «أقل من 90»)،
        فالتصنيفُ يُحسب على المجموع المرجَّح **غير المقرَّب** — 89.5 جيد جداً لا ممتاز،
        و75.3 جيد جداً لا جيد، و49.5 ضعيف لا مقبول. أمّا `total_score` المخزَّن فعددٌ
        صحيحٌ للعرض، يُقرَّب كما كان.
        """
        if total >= _SCORE_EXCELLENT:
            return "excellent"
        if total > _SCORE_VERY_GOOD_ABOVE:
            return "very_good"
        if total > _SCORE_GOOD_ABOVE:
            return "good"
        if total >= _SCORE_ACCEPTABLE:
            return "acceptable"
        return "weak"

    @classmethod
    def total_for(cls, exact: int | Fraction) -> int:
        """
        المجموعُ المخزَّن للعرض: أقربُ عددٍ صحيحٍ **داخل نطاق مستواه المطبوع** (مفتاحُ
        الاستمارات 100–90 / 89–76 / 75–66 / 65–50 / 0–49، 06 §2.2).

        المستوى من الكسر (المادة 16، `rating_for`)، ومفتاحُ الاستمارة أعدادٌ صحيحة. فالتقريبُ
        العاديّ كان يعرض 89.5 «90» بجوار «جيد جداً (89–76)»، و75.3 «75» بجوار «جيد جداً».
        فإن عبر التقريبُ حدَّ المستوى أُخذ الجزءُ الصحيحُ في جهة المستوى. اختيارٌ هندسيّ.
        """
        rounded = round(exact)
        level = cls.rating_for(exact)
        if cls.rating_for(rounded) == level:
            return int(rounded)
        return math.floor(exact) if rounded > exact else math.ceil(exact)

    def calculate_total(self) -> None:
        """حساب المجموع من المحاور الأربعة الافتراضية + التقدير"""
        self.total_score = (
            self.axis_professional
            + self.axis_commitment
            + self.axis_teamwork
            + self.axis_development
        )
        self.rating = self.rating_for(self.total_score)
        self._drop_level_off_form()

    def calculate_weighted_total(self) -> None:
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
            exact = Fraction(weighted_sum, total_weight)
            self.total_score = self.total_for(exact)
        else:
            self.calculate_total()
            return

        # التصنيفُ على المجموع غير المقرَّب — انظر `rating_for` (المادة 16).
        self.rating = self.rating_for(exact)
        self._drop_level_off_form()

    def _drop_level_off_form(self) -> None:
        """
        التقريرُ السنويّ يوضع «وفقاً للنماذج المعتمدة من الوزير» (المادة 15، صفحة الملفّ 10،
        02_staff_affairs.md:199)، ومستوياتُ المادة 16 مستوياتُه — تترتّب عليها آثارُ المادتين
        21 و22. فصفُّ S2 ليس على الاستمارة (المحاورُ الأربعة قبل الموجة، أو مفاتيحُ غريبة)
        لا يأخذ اسمَ مستوىً منها. والمتابعةُ الداخليّة S1 على السُّلَّم الواحد (ADR-0002 §6.3).
        """
        if self.period == self.MINISTRY_PERIOD and not self.has_form_scores():
            self.rating = ""

    def settle_level_after_scores(self) -> None:
        """
        بعد أن تُكتب درجاتُ مقيِّمٍ في `EvaluationScore`: المستوى على الصفوف كما هي الآن. والحفظُ
        بـ`update_fields` بلا حقول المحاور لا يمرّ بـ`_drop_level_off_form` في `save()`، فمن
        كتب الدرجاتَ يستدعي هذا قبل الحفظ. ويُسقط ما جُلب مسبقاً من `scores` لأنّه قبل الكتابة.
        """
        prefetched = getattr(self, "_prefetched_objects_cache", None)
        if prefetched:
            prefetched.pop("scores", None)
        self._drop_level_off_form()

    def save(self, *args: Any, **kwargs: Any) -> None:
        # إصلاح #3: حساب المجموع فقط عندما لا يكون update_fields محدداً
        # أو عندما تتضمن update_fields أحد حقول المحاور
        update_fields = kwargs.get("update_fields")
        if update_fields is None or self._AXIS_FIELDS & set(update_fields):
            # تقييمٌ على قالب دورٍ درجاتُه في `EvaluationScore.custom_axes` لا في حقول المحاور
            # الأربعة (وهي أصفار) — فحسابُه منها يصفّره. كان حفظُه من لوحة الإدارة لتغيير
            # الحالة يجعل المعتمَدَ 0 و«يحتاج تطوير».
            if self.has_template_scores():
                self.calculate_weighted_total()
            else:
                self.calculate_total()
            # إضافة total_score و rating لقائمة update_fields إذا كانت محددة
            if update_fields is not None:
                update_fields = list(update_fields)
                for f in ("total_score", "rating"):
                    if f not in update_fields:
                        update_fields.append(f)
                kwargs["update_fields"] = update_fields
        super().save(*args, **kwargs)

    def has_template_scores(self) -> bool:
        """أمحفوظٌ على قالب دورٍ بدرجات مقيِّمين؟ (فمجموعُه من `scores` لا من حقول المحاور)."""
        return not self._state.adding and self.template_id is not None and self.scores.exists()

    def has_form_scores(self) -> bool:
        """
        أدرجاتُه درجاتُ استمارة قالبه؟ مربوطٌ بقالبٍ هو استمارةُ دوره (`matches_ministry_form`:
        كان يكفي أيُّ قالبٍ له محاور، ولوحةُ الإدارة كانت تكتبه)، وعنده صفُّ درجاتٍ واحدٌ على الأقلّ،
        ومفاتيحُ كلِّ صفٍّ هي مفاتيحُ محاور القالب بعينها. كان يكفي وجودُ `EvaluationScore`، فصفٌّ
        أُدخلت درجاتُه من لوحة الإدارة بمفاتيحَ أخرى يُجمع ويُعتمد تقريراً سنويّاً.
        (يقرأ `.all()` ليكفيه `prefetch_related("scores", "template__axes")`.)
        """
        template = None if self._state.adding or self.template_id is None else self.template
        if template is None or not template.matches_ministry_form():
            return False
        keys = {axis.key for axis in template.axes.all()}
        rows = [score.custom_axes or {} for score in self.scores.all()]
        return bool(keys) and bool(rows) and all(set(row) == keys for row in rows)

    def has_default_axis_scores(self) -> bool:
        """
        أدرجاتُه في المحاور الافتراضيّة الأربعة (لا عند مقيِّم) ولو كان مربوطاً بقالب؟

        صفوفٌ قديمةٌ حُفظت على المحاور الأربعة ثمّ ربطها الـGET القديم بقالب دورها: درجاتُها
        في الحقول، ولا `EvaluationScore` لها. فالنظرُ إلى `template_id` وحدَه كان يعرضها
        أصفاراً على محاور الاستمارة ويصفّرها عند أوّل حفظ.
        """
        if self._state.adding:
            return False
        return any(getattr(self, f) for f in self._AXIS_FIELDS) and not self.scores.exists()

    def has_saved_content(self) -> bool:
        """
        أعليه ما يُفقَد لو رُبط بقالبٍ آخر؟ درجاتٌ في المحاور الافتراضيّة أو عند مقيِّم،
        أو حالةٌ تجاوزت المسودّة.
        """
        if self._state.adding:
            return False
        if self.status != "draft" or self.total_score:
            return True
        if any(getattr(self, f) for f in self._AXIS_FIELDS):
            return True
        return self.scores.exists()

    def clean(self) -> None:
        """
        تظلّمٌ لا يُقبل تدوينُه بعد فوات ميعاده: «ويجوز للموظف أن يتظلم منه ... خلال خمسة
        عشر يوماً من تاريخ علمه» (المادة 20، صفحة الملفّ 12). وحقولُ التظلّم تُحرَّر من
        لوحة الإدارة، فالفحصُ على النموذج لا على الشاشة.
        """
        super().clean()
        errors = self._grievance_order_errors()
        if self.grievance_outcome and self.grievance_decided_on is None:
            errors["grievance_outcome"] = "قرارٌ بلا تاريخ إخطار الموظّف به (المادة 20)."
        deadline = self.grievance_deadline()
        if (
            "grievance_submitted_on" not in errors
            and self.grievance_submitted_on is not None
            and deadline is not None
            and self.grievance_submitted_on > deadline
        ):
            errors["grievance_submitted_on"] = (
                f"ميعادُ التظلّم انقضى في {deadline} — «خلال خمسة عشر يوماً من "
                "تاريخ علمه» (المادة 20)."
            )
        if errors:
            raise ValidationError(errors)

    def _grievance_order_errors(self) -> dict[str, str]:
        """
        تسلسلُ المادة 20 (صفحتا الملفّ 12–13): «يُعلن الموظف بنسخة من تقرير تقييم الأداء،
        ويجوز للموظف أن يتظلم منه ... خلال خمسة عشر يوماً من تاريخ علمه، وتبت اللجنة في
        التظلم خلال ثلاثين يوماً من تاريخ تقديمه ... ويكون قرار اللجنة في التظلم نهائياً بعد
        اعتماده من الوزير». فالتظلّمُ بعد العلم بتقريرٍ معتمَد، والقرارُ واعتمادُه بعد التظلّم،
        ولا تاريخَ منها في الغد. وأيُّ الاثنين أسبق — إخطارُ الموظّف بالقرار أم اعتمادُ الوزير
        له — لا يقوله النصّ، فلا يُفرض بينهما ترتيب.
        """
        errors: dict[str, str] = {}
        today = timezone.localdate()
        submitted = self.grievance_submitted_on
        known_on = self.known_on() if self.status in ("approved", "acknowledged") else None
        dates = {
            "grievance_submitted_on": submitted,
            "grievance_decided_on": self.grievance_decided_on,
            "grievance_decision_approved_on": self.grievance_decision_approved_on,
        }
        for field, value in dates.items():
            if value is None:
                continue
            if value > today:
                errors[field] = "تاريخٌ لم يأتِ بعد."
            elif known_on is None:
                errors[field] = (
                    "لا تظلّمَ قبل أن يُعلَم الموظّفُ بتقريرٍ معتمَد — «يُعلن الموظف بنسخة من "
                    "تقرير تقييم الأداء، ويجوز للموظف أن يتظلم منه» (المادة 20)."
                )
            elif field == "grievance_submitted_on":
                if value < known_on:
                    errors[field] = (
                        f"قبل تاريخ علمه ({known_on}) — «خلال خمسة عشر يوماً من تاريخ علمه» "
                        "(المادة 20)."
                    )
            elif submitted is None:
                errors[field] = "لا قرارَ للجنة ولا اعتمادَ له بلا تظلّمٍ مقدَّم (المادة 20)."
            elif value < submitted:
                errors[field] = (
                    f"قبل تقديم التظلّم ({submitted}) — «وتبت اللجنة في التظلم خلال ثلاثين "
                    "يوماً من تاريخ تقديمه» (المادة 20)."
                )
        return errors

    def known_on(self) -> date | None:
        """
        «تاريخ علمه» (المادة 20): إقرارُ الموظّف بالاستلام، أو تاريخُ الاستلام الذي يدوّنه
        المدير حين يرفض الموظّف التوقيع (استمارة المعلم ص2).

        وإن اجتمعا فالأسبقُ منهما: العلمُ واقعةٌ لا تتكرّر، فإقرارٌ يُوقَّع بعد شهرين من
        تاريخ الاستلام المدوَّن كان يؤخّر المهلةَ ويعيد فتح تظلّمٍ انقضى ميعادُه.
        """
        dates = [d for d in (self._acknowledged_on(), self.received_on) if d is not None]
        return min(dates) if dates else None

    def _acknowledged_on(self) -> date | None:
        if self.acknowledged_at is None:
            return None
        return timezone.localtime(self.acknowledged_at).date()

    def grievance_deadline(self) -> date | None:
        """آخرُ يومٍ للتظلّم: خمسة عشر يوماً من تاريخ العلم (المادة 20)."""
        known_on = self.known_on()
        if known_on is None:
            return None
        return known_on + _grievance_days(
            "APPRAISAL_GRIEVANCE_WINDOW_DAYS", APPRAISAL_GRIEVANCE_WINDOW_DAYS
        )

    def is_final(self, today: date | None = None) -> bool:
        """
        «ولا يعتبر التقرير نهائياً إلا بعد انقضاء ميعاد التظلم منه أو البت فيه» (المادة 20).

        - بلا تظلّم: بانقضاء الخمسة عشر يوماً من تاريخ العلم.
        - قرارُ اللجنة: «نهائياً بعد اعتماده من الوزير» — فلا يكفي إخطارُ الموظّف به.
        - مضيُّ ثلاثين يوماً من التظلّم «دون إخطار الموظف بتعديل التقرير»: «بمثابة قرار
          بالرفض». وأيحتاج هذا الرفضُ الحكميُّ اعتمادَ الوزير؟ النصُّ صامت (ADR-0002 §6.6
          بند 13)؛ فيُعدّ بتّاً كما كان.
        ولا تُبنى على المستوى آثارُه (الحافز م21، الترقية م22) قبل ذلك.
        """
        deadline = self.grievance_deadline()
        if self.status not in ("approved", "acknowledged") or deadline is None:
            return False
        today = today or timezone.localdate()
        # تظلّمٌ قُدّم بعد انقضاء الخمسة عشر يوماً لا يقبله النصّ («خلال خمسة عشر يوماً من
        # تاريخ علمه»)، فلا يُسقط نهائيّةً ثبتت بانقضاء الميعاد. وكان تدوينُه من لوحة الإدارة
        # يعيد فتح تقريرٍ نهائيٍّ بلا حدّ.
        if self.grievance_submitted_on is not None and self.grievance_submitted_on > deadline:
            return True
        # بلا تظلّمٍ مقدَّم لا قرارَ للجنة ولا اعتمادَ له: الحقلان وحدهما (تدوينٌ خاطئٌ من لوحة
        # الإدارة) لا يُنهيان مهلةَ الموظّف ولا يعلّقانها — ولا اعتمادَ قبل التظلّم أو بعد اليوم.
        submitted = self.grievance_submitted_on
        if submitted is None:
            return bool(today > deadline)
        approved_on = self.grievance_decision_approved_on
        if approved_on is not None and submitted <= approved_on <= today:
            return True
        decision_by = submitted + _grievance_days(
            "APPRAISAL_GRIEVANCE_DECISION_DAYS", APPRAISAL_GRIEVANCE_DECISION_DAYS
        )
        # إخطارٌ في الميعاد قرارُ لجنةٍ ينتظر اعتمادَ الوزير. أمّا بعده فالرفضُ الحكميُّ قد وقع
        # («ويعتبر انقضاء الميعاد المذكور دون إخطار الموظف بتعديل التقرير بمثابة قرار بالرفض»،
        # صفحة الملفّ 13) — وكان تدوينُ إخطارٍ متأخّرٍ يعيد فتحَ تقريرٍ نهائيٍّ بلا حدّ.
        decided_on = self.grievance_decided_on
        if decided_on is not None and decided_on <= decision_by:
            return False
        return bool(today > decision_by)

    def acknowledge(self):
        """
        إقرارُ الموظّف بالاستلام ومعه تعليقُه (`employee_comment`، يضعه العرضُ قبل النداء).
        كان التعليقُ خارج `update_fields` فيضيع صامتاً — وهو أوّلُ ما يُبنى عليه التظلّم
        («ويجوز للموظف أن يتظلم منه»، المادة 20، صفحة الملفّ 12).
        """
        self.status = "acknowledged"
        self.acknowledged_at = timezone.now()
        self.save(update_fields=["status", "acknowledged_at", "employee_comment", "updated_at"])

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
        CustomUser,
        on_delete=models.CASCADE,
        related_name="evaluation_scores_given",
        verbose_name="المقيِّم",
    )
    weight = models.PositiveSmallIntegerField(
        default=100,
        verbose_name="الوزن (%)",
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
        default=dict,
        blank=True,
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
        return f"{self.evaluator.full_name} → {self.evaluation.employee.full_name} ({self.weight}%)"

    def calculate_total(self) -> None:
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
        # `update_or_create` يحفظ بـ`update_fields` الحقولَ التي مرّرها وحدها (Django ≥4.2)،
        # فكان المجموعُ يُحسب ولا يُكتب، ويبقى قديماً فيُفسد المجموعَ المرجَّح.
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "total_score" not in update_fields:
            kwargs["update_fields"] = [*update_fields, "total_score"]
        super().save(*args, **kwargs)


class EvaluationLevelBackup(models.Model):
    """
    ما كان عليه مجموعُ التقرير ومستواه قبل أن تعيد الهجرة 0018 حسابَهما: عتباتُ المادة 16
    (صفحتا الملفّ 10–11)، والتقريرُ السنويّ خارج الاستمارة بلا مستوى (المادة 15، صفحة الملفّ 10).
    تغييرُ الهجرة صامت — تقريرٌ أقرّ به الموظّف يفقد مستواه — فهذا سجلُّه، ومنه يسترجع العكسُ
    ما محاه. للقراءة وحدها.
    """

    evaluation = models.OneToOneField(
        EmployeeEvaluation, on_delete=models.CASCADE, related_name="+", verbose_name="التقييم"
    )
    old_total_score = models.PositiveSmallIntegerField(verbose_name="المجموع قبل الهجرة")
    old_rating = models.CharField(max_length=15, blank=True, verbose_name="المستوى قبل الهجرة")
    new_total_score = models.PositiveSmallIntegerField(verbose_name="المجموع بعد الهجرة")
    new_rating = models.CharField(max_length=15, blank=True, verbose_name="المستوى بعد الهجرة")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "مستوى تقييمٍ قبل الهجرة 0018"
        verbose_name_plural = "مستويات التقييم قبل الهجرة 0018"

    def __str__(self) -> str:
        return (
            f"#{self.evaluation_id}: {self.old_total_score}/{self.old_rating or '—'}"
            f" ← {self.new_total_score}/{self.new_rating or '—'}"
        )


class EvaluationCycle(models.Model):
    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="eval_cycles")
    academic_year = models.CharField(max_length=9, default=default_academic_year)
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

    def article_16_window(self) -> tuple[date, date] | None:
        """
        «ويعتمد من مدير المدرسة خلال النصف الأول من شهر يونيو من كل عام أكاديمي» (المادة 16،
        02_staff_affairs.md:200) — 1–15 يونيو من العام الذي ينتهي به العامُ الأكاديميّ،
        للتقرير السنويّ (S2) وحده. وتحويلُ النصّ إلى تاريخين تطبيقٌ على التقويم.
        """
        if self.period != EmployeeEvaluation.MINISTRY_PERIOD:
            return None
        try:
            end_year = int(str(self.academic_year).split("-")[1])
        except (IndexError, ValueError):
            return None
        return date(end_year, 6, 1), date(end_year, 6, 15)

    @property
    def deadline_outside_article_16(self) -> bool:
        """تنبيهٌ لا منع: موعدُ دورة S2 خارج النصف الأوّل من يونيو."""
        window = self.article_16_window()
        return bool(window) and not (window[0] <= self.deadline <= window[1])

    # إصلاح #4: cached_property لتجنب 2×N queries
    @cached_property
    def completion_rate(self):
        """
        نسبةُ من وُضع تقريرُه من الموظّفين الذين يُفتح لهم تقريرُ الفترة.

        والتقريرُ السنويّ (S2) لا يُفتح إلّا لدورٍ له استمارةٌ وزاريّة («وفقاً للنماذج المعتمدة
        من الوزير» — المادة 15، 02_staff_affairs.md:199)؛ والأدوارُ التي لم يسمِّ المصدرُ
        استمارتَها معلّقةٌ للمالك (ADR-0002 §6.6 بند 12). فكانت تدخل المقام ولا سبيلَ إلى
        تقريرها، فلا تبلغ الدورةُ 100% أبداً. والبسطُ من المقام نفسه — لا يُعدّ تقريرٌ لمن
        ليس فيه.
        """
        roles = set(_EVALUABLE_ROLES)
        if self.period == EmployeeEvaluation.MINISTRY_PERIOD:
            roles &= set(forms_by_role())
        staff_ids = Membership.objects.filter(
            school=self.school,
            is_active=True,
            role__name__in=roles,
        ).values("user_id")
        # بلا ترتيبٍ افتراضيّ: حقولُ الترتيب تدخل DISTINCT فيُعدّ الموظّفُ مرّتين.
        total_staff = staff_ids.order_by().distinct().count()
        placed = EmployeeEvaluation.objects.filter(
            school=self.school,
            academic_year=self.academic_year,
            period=self.period,
            status__in=["submitted", "approved", "acknowledged"],
            employee_id__in=staff_ids,
        )
        if self.period == EmployeeEvaluation.MINISTRY_PERIOD:
            # تقريرٌ سنويٌّ ليس على درجات الاستمارة لا يُعتمد (`approve_evaluation`) — فلا يُعدّ
            # منجزاً؛ كان مُقدَّمٌ على قالبٍ خرج عن الاستمارة يُكمل الدورةَ ولا سبيلَ إلى اعتماده.
            rows = placed.select_related("template").prefetch_related("scores", "template__axes")
            evaluated = sum(1 for row in rows if row.has_form_scores())
        else:
            evaluated = placed.count()
        return round(evaluated / total_staff * 100) if total_staff else 0


# ── الإشراف على أداء المعلّم (الملاحظة الصفّية) — وحدة مستقلّة ──────────
from quality.observation_models import (  # noqa: E402,F401
    ClassroomObservation,
    ObservationCriterion,
    ObservationScore,
)
