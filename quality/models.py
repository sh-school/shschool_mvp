"""
quality/models.py
الخطة التشغيلية + لجنة المراجعة الذاتية + ربط المنفذين
الهيكل الهرمي: مجال → هدف → مؤشر → إجراء → دليل
"""
import uuid
from django.db import models
from django.utils import timezone
from core.models import School, CustomUser


def _uuid():
    return uuid.uuid4()


# ─────────────────────────────────────────────
# 1. الهيكل الهرمي للخطة التشغيلية
# ─────────────────────────────────────────────

class OperationalDomain(models.Model):
    """المجال: التحصيل الأكاديمي / القيادة والإدارة / ..."""
    id            = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school        = models.ForeignKey(School, on_delete=models.CASCADE, related_name="op_domains")
    name          = models.CharField(max_length=200, verbose_name="اسم المجال")
    academic_year = models.CharField(max_length=9, default="2025-2026")
    order         = models.IntegerField(default=0)

    class Meta:
        verbose_name        = "مجال"
        verbose_name_plural = "المجالات"
        ordering            = ["order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["school", "name", "academic_year"], name="unique_domain_per_year")
        ]

    def __str__(self):
        return self.name

    @property
    def total_procedures(self):
        return OperationalProcedure.objects.filter(indicator__target__domain=self).count()

    @property
    def completed_procedures(self):
        return OperationalProcedure.objects.filter(
            indicator__target__domain=self, status="Completed"
        ).count()

    @property
    def completion_pct(self):
        total = self.total_procedures
        return round(self.completed_procedures / total * 100) if total else 0


class OperationalTarget(models.Model):
    id     = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    domain = models.ForeignKey(OperationalDomain, on_delete=models.CASCADE, related_name="targets")
    number = models.CharField(max_length=20, verbose_name="رقم الهدف")
    text   = models.TextField(verbose_name="نص الهدف")

    class Meta:
        verbose_name        = "هدف"
        verbose_name_plural = "الأهداف"
        ordering            = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["domain", "number"], name="unique_target_in_domain")
        ]

    def __str__(self):
        return f"[{self.number}] {self.text[:60]}"


class OperationalIndicator(models.Model):
    id     = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    target = models.ForeignKey(OperationalTarget, on_delete=models.CASCADE, related_name="indicators")
    number = models.CharField(max_length=30, verbose_name="رقم المؤشر")
    text   = models.TextField(verbose_name="نص المؤشر")

    class Meta:
        verbose_name        = "مؤشر"
        verbose_name_plural = "المؤشرات"
        ordering            = ["number"]

    def __str__(self):
        return f"[{self.number}] {self.text[:60]}"


class OperationalProcedure(models.Model):
    STATUS = [
        ("In Progress", "قيد التنفيذ"),
        ("Completed",   "مكتمل"),
        ("Cancelled",   "ملغى"),
        ("Not Started", "لم يبدأ"),
    ]
    EVIDENCE_TYPE = [
        ("وصفي",       "وصفي"),
        ("كمي",        "كمي"),
        ("كمي/وصفي",  "كمي/وصفي"),
        ("",           "—"),
    ]

    id            = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    indicator     = models.ForeignKey(OperationalIndicator, on_delete=models.CASCADE, related_name="procedures")
    school        = models.ForeignKey(School, on_delete=models.CASCADE, related_name="procedures")
    number        = models.CharField(max_length=30, verbose_name="رقم الإجراء", db_index=True)
    text          = models.TextField(verbose_name="نص الإجراء")

    # المنفذ — نص + مستخدم مربوط
    executor_norm = models.CharField(max_length=100, verbose_name="المنفذ (نص)", db_index=True)
    executor_user = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assigned_procedures", verbose_name="المنفذ (مستخدم)"
    )

    date_range           = models.CharField(max_length=50, verbose_name="الفترة الزمنية", blank=True)
    status               = models.CharField(max_length=15, choices=STATUS, default="In Progress", db_index=True)
    evaluation           = models.TextField(blank=True, verbose_name="التقييم")
    evaluation_notes     = models.TextField(blank=True, verbose_name="ملاحظات التقييم")
    follow_up            = models.TextField(blank=True, verbose_name="المتابعة")
    comments             = models.TextField(blank=True, verbose_name="تعليقات")
    evidence_type        = models.CharField(max_length=20, choices=EVIDENCE_TYPE, blank=True)
    evidence_source_employee = models.TextField(blank=True, verbose_name="موظف مصدر الدليل")
    evidence_source_file = models.TextField(blank=True, verbose_name="ملف مصدر الدليل")

    academic_year = models.CharField(max_length=9, default="2025-2026")
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "إجراء"
        verbose_name_plural = "الإجراءات"
        ordering            = ["number"]
        indexes = [
            models.Index(fields=["school", "status"]),
            models.Index(fields=["executor_norm"]),
            models.Index(fields=["school", "academic_year"]),
        ]

    def __str__(self):
        return f"[{self.number}] {self.text[:60]}"


class ProcedureEvidence(models.Model):
    id          = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    procedure   = models.ForeignKey(OperationalProcedure, on_delete=models.CASCADE, related_name="evidences")
    uploaded_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name="uploaded_evidences")
    title       = models.CharField(max_length=200, verbose_name="عنوان الدليل")
    description = models.TextField(blank=True)
    file        = models.FileField(upload_to="evidence/%Y/%m/", null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "دليل"
        verbose_name_plural = "الأدلة"
        ordering            = ["-created_at"]

    def __str__(self):
        return f"{self.title} — {self.procedure.number}"


# ─────────────────────────────────────────────
# 2. ربط المنفذين بالمستخدمين ← الجديد
# ─────────────────────────────────────────────

class ExecutorMapping(models.Model):
    """
    ربط المسمى الوظيفي (executor_norm) بمستخدم حقيقي.

    بعد الربط، تُحدَّث executor_user في كل الإجراءات المرتبطة
    بهذا المسمى تلقائياً عبر apply_mapping().
    """
    id            = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school        = models.ForeignKey(School, on_delete=models.CASCADE, related_name="executor_mappings")
    executor_norm = models.CharField(max_length=100, verbose_name="المسمى الوظيفي", db_index=True)
    user          = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="executor_mappings", verbose_name="الموظف"
    )
    academic_year = models.CharField(max_length=9, default="2025-2026")
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "ربط منفذ"
        verbose_name_plural = "ربط المنفذين"
        ordering            = ["executor_norm"]
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


# ─────────────────────────────────────────────
# 3. لجنة تنفيذ الخطة التشغيلية
# ─────────────────────────────────────────────

class QualityCommitteeMember(models.Model):
    """عضو في لجنة المراجعة الذاتية / تنفيذ الخطة التشغيلية"""
    RESPONSIBILITY = [
        ("رئيس اللجنة",      "رئيس اللجنة"),
        ("نائب رئيس اللجنة", "نائب رئيس اللجنة"),
        ("مقرر",             "مقرر"),
        ("عضو",              "عضو"),
    ]

    id             = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school         = models.ForeignKey(School, on_delete=models.CASCADE, related_name="quality_members")
    user           = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="quality_memberships",
        null=True, blank=True
    )
    job_title      = models.CharField(max_length=100, verbose_name="المسمى الوظيفي")
    responsibility = models.CharField(max_length=30, choices=RESPONSIBILITY, verbose_name="المسؤولية")
    domain         = models.ForeignKey(
        OperationalDomain, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="committee_members", verbose_name="المجال المسؤول عنه"
    )
    academic_year  = models.CharField(max_length=9, default="2025-2026")
    is_active      = models.BooleanField(default=True)

    class Meta:
        verbose_name        = "عضو لجنة جودة"
        verbose_name_plural = "أعضاء لجنة الجودة"
        ordering            = ["responsibility", "job_title"]

    def __str__(self):
        name = self.user.full_name if self.user else self.job_title
        return f"{name} — {self.responsibility}"
