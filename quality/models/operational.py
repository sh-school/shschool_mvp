"""الخطّة التشغيليّة: الهيكلُ الهرميّ (مجال ← هدف ← مؤشّر ← إجراء ← دليل)، وسجلُّ حالة الإجراء، وربطُ المنفّذين بالمسمّيات."""

from datetime import timedelta

from django.db import models
from django.utils import timezone

from core.academic_calendar import default_academic_year
from core.models import CustomUser, School

from .common import _uuid

# ─────────────────────────────────────────────────────────────
# 1. الهيكل الهرمي للخطة التشغيلية
# ─────────────────────────────────────────────────────────────


class OperationalDomain(models.Model):
    """المجال: التحصيل الأكاديمي / القيادة والإدارة / ..."""

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="op_domains", verbose_name="المدرسة"
    )
    name = models.CharField(max_length=200, verbose_name="اسم المجال")
    academic_year = models.CharField(
        max_length=9, default=default_academic_year, verbose_name="العام الدراسي"
    )
    order = models.IntegerField(default=0, verbose_name="الترتيب")

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
    domain = models.ForeignKey(
        OperationalDomain, on_delete=models.CASCADE, related_name="targets", verbose_name="المجال"
    )
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
        OperationalTarget, on_delete=models.CASCADE, related_name="indicators", verbose_name="الهدف"
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
        OperationalIndicator,
        on_delete=models.CASCADE,
        related_name="procedures",
        verbose_name="المؤشّر",
    )
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="procedures", verbose_name="المدرسة"
    )
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
    status = models.CharField(
        max_length=20, choices=STATUS, default="In Progress", db_index=True, verbose_name="الحالة"
    )
    evaluation = models.TextField(blank=True, verbose_name="التقييم")
    evaluation_notes = models.TextField(blank=True, verbose_name="ملاحظات التقييم")
    follow_up = models.TextField(blank=True, verbose_name="المتابعة")
    comments = models.TextField(blank=True, verbose_name="تعليقات")
    evidence_type = models.CharField(
        max_length=20, choices=EVIDENCE_TYPE, blank=True, verbose_name="نوع الشاهد"
    )
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

    academic_year = models.CharField(
        max_length=9, default=default_academic_year, verbose_name="العام الدراسي"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التعديل")

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
        OperationalProcedure,
        on_delete=models.CASCADE,
        related_name="evidences",
        verbose_name="الإجراء التشغيلي",
    )
    uploaded_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="uploaded_evidences",
        verbose_name="رفعه",
    )
    title = models.CharField(max_length=200, verbose_name="عنوان الدليل")
    description = models.TextField(blank=True, verbose_name="الوصف")
    file = models.FileField(
        upload_to="evidence/%Y/%m/", null=True, blank=True, verbose_name="الملف"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

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
        verbose_name="الإجراء التشغيلي",
    )
    old_status = models.CharField(max_length=20, verbose_name="الحالة السابقة")
    new_status = models.CharField(max_length=20, verbose_name="الحالة الجديدة")
    changed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="procedure_status_changes",
        verbose_name="غيّر الحالة",
    )
    note = models.TextField(blank=True, verbose_name="ملاحظة")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

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
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="executor_mappings", verbose_name="المدرسة"
    )
    executor_norm = models.CharField(max_length=100, verbose_name="المسمى الوظيفي", db_index=True)
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="executor_mappings",
        verbose_name="الموظف",
    )
    academic_year = models.CharField(
        max_length=9, default=default_academic_year, verbose_name="العام الدراسي"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التعديل")

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
