from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.db import models
from django.utils import timezone

from .school import School, _uuid
from .user import CustomUser


class _ImmutableQuerySet(models.QuerySet):
    """QuerySet that blocks bulk delete/update — PDPPL م.19"""

    def delete(self):
        raise PermissionDenied("AuditLog records are immutable and cannot be deleted.")

    def update(self, **kwargs):
        raise PermissionDenied("AuditLog records are immutable and cannot be updated.")


class _ImmutableManager(models.Manager):
    def get_queryset(self):
        return _ImmutableQuerySet(self.model, using=self._db)


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ("create", "إنشاء"),
        ("update", "تعديل"),
        ("delete", "حذف"),
        ("view", "عرض"),
        ("export", "تصدير"),
        ("login", "تسجيل دخول"),
        ("logout", "تسجيل خروج"),
    ]
    MODEL_CHOICES = [
        ("HealthRecord", "سجل صحي"),
        ("BehaviorInfraction", "مخالفة سلوكية"),
        ("StudentSubjectResult", "درجة طالب"),
        ("ClinicVisit", "زيارة عيادة"),
        ("CustomUser", "مستخدم"),
        ("ParentStudentLink", "ربط ولي أمر"),
        ("BookBorrowing", "إعارة كتاب"),
        ("ConsentRecord", "سجل موافقة"),
        ("StudentAssessmentGrade", "درجة تقييم"),
        ("other", "أخرى"),
    ]

    objects = _ImmutableManager()

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, related_name="audit_logs"
    )
    user = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, related_name="audit_actions"
    )
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=50, choices=MODEL_CHOICES, default="other")
    object_id = models.CharField(max_length=100, blank=True)
    object_repr = models.CharField(max_length=300, blank=True, verbose_name="وصف السجل")
    changes = models.JSONField(null=True, blank=True, verbose_name="التغييرات")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "سجل مراجعة"
        verbose_name_plural = "سجلات المراجعة"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["school", "timestamp"]),
            models.Index(fields=["model_name", "object_id"]),
            models.Index(fields=["user", "timestamp"]),
        ]

    def __str__(self):
        return f"{self.user} | {self.action} | {self.model_name} | {self.timestamp:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs):
        if self.pk and AuditLog.objects.filter(pk=self.pk).exists():
            raise PermissionDenied("AuditLog records are immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("AuditLog records are immutable and cannot be deleted.")

    @classmethod
    def log(
        cls,
        *,
        user,
        action,
        model_name,
        object_id="",
        object_repr="",
        changes=None,
        school=None,
        request=None,
    ):
        ip = ua = ""
        if request:
            ip = request.META.get("REMOTE_ADDR")
            ua = request.META.get("HTTP_USER_AGENT", "")[:300]
            if not school and hasattr(request.user, "get_school"):
                school = request.user.get_school()
        cls.objects.create(
            user=user,
            action=action,
            model_name=model_name,
            object_id=str(object_id),
            object_repr=str(object_repr)[:300],
            changes=changes,
            school=school,
            ip_address=ip,
            user_agent=ua,
        )


class ConsentRecord(models.Model):
    DATA_TYPES = [
        ("health", "البيانات الصحية"),
        ("behavior", "بيانات السلوك"),
        ("grades", "الدرجات والتقييمات"),
        ("attendance", "الحضور والغياب"),
        ("transport", "بيانات النقل"),
        ("photo", "الصور والمرئيات"),
        ("all", "جميع البيانات"),
    ]
    METHODS = [
        ("form", "استمارة ورقية"),
        ("digital", "موافقة رقمية"),
        ("verbal", "موافقة شفهية موثقة"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    parent = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="consent_records")
    student = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="consent_as_student"
    )
    data_type = models.CharField(max_length=20, choices=DATA_TYPES)
    is_given = models.BooleanField(default=True, verbose_name="تمت الموافقة")
    method = models.CharField(max_length=10, choices=METHODS, default="digital")
    given_at = models.DateTimeField(auto_now_add=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, related_name="consents_recorded"
    )

    class Meta:
        verbose_name = "سجل موافقة"
        verbose_name_plural = "سجلات الموافقة"
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "student", "data_type"],
                name="unique_consent_per_parent_student_type",
            )
        ]
        ordering = ["-given_at"]

    def __str__(self):
        status = "موافق" if self.is_given else "مسحوب"
        return (
            f"{self.parent.full_name} ← {self.student.full_name} "
            f"| {self.get_data_type_display()} | {status}"
        )

    def withdraw(self):
        self.is_given = False
        self.withdrawn_at = timezone.now()


class BreachReport(models.Model):
    """تقرير خرق البيانات — PDPPL م.11 / إشعار NCSA خلال 72 ساعة"""

    SEVERITY = [
        ("low", "منخفضة"),
        ("medium", "متوسطة"),
        ("high", "عالية"),
        ("critical", "حرجة"),
    ]
    STATUS = [
        ("discovered", "مكتشف"),
        ("assessing", "قيد التقييم"),
        ("notified", "تم الإشعار"),
        ("resolved", "محلول"),
    ]
    DATA_TYPES_AFFECTED = [
        ("health", "بيانات صحية"),
        ("academic", "بيانات أكاديمية"),
        ("personal", "بيانات شخصية"),
        ("financial", "بيانات مالية"),
        ("all", "جميع البيانات"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="breach_reports")
    title = models.CharField(max_length=300, verbose_name="عنوان الخرق")
    description = models.TextField(verbose_name="وصف الخرق التفصيلي")
    severity = models.CharField(max_length=10, choices=SEVERITY, default="medium")
    data_type_affected = models.CharField(
        max_length=15,
        choices=DATA_TYPES_AFFECTED,
        default="personal",
        verbose_name="نوع البيانات المتأثرة",
    )
    affected_count = models.PositiveIntegerField(default=0, verbose_name="عدد الأشخاص المتأثرين")
    discovered_at = models.DateTimeField(verbose_name="وقت الاكتشاف")
    created_at = models.DateTimeField(auto_now_add=True)
    ncsa_deadline = models.DateTimeField(
        null=True, blank=True, verbose_name="موعد إشعار NCSA (72 ساعة)"
    )
    ncsa_notified_at = models.DateTimeField(
        null=True, blank=True, verbose_name="وقت إشعار NCSA الفعلي"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=STATUS, default="discovered")
    reported_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, related_name="reported_breaches"
    )
    assigned_to = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_breaches",
        verbose_name="المسؤول (DPO)",
    )
    immediate_action = models.TextField(blank=True, verbose_name="الإجراء الفوري المتخذ")
    containment_action = models.TextField(blank=True, verbose_name="إجراءات الاحتواء")
    notification_text = models.TextField(blank=True, verbose_name="نص الإشعار لـ NCSA")
    evidence_notes = models.TextField(blank=True, verbose_name="الأدلة والملاحظات")

    class Meta:
        verbose_name = "تقرير خرق بيانات"
        verbose_name_plural = "تقارير خرق البيانات"
        ordering = ["-discovered_at"]
        indexes = [
            models.Index(fields=["school", "status"]),
            models.Index(fields=["discovered_at"]),
        ]

    def __str__(self):
        return f"{self.title} | {self.get_severity_display()} | {self.get_status_display()}"

    def save(self, *args, **kwargs):
        if self.discovered_at and not self.ncsa_deadline:
            self.ncsa_deadline = self.discovered_at + timedelta(hours=72)
        super().save(*args, **kwargs)

    @property
    def hours_remaining(self):
        if self.ncsa_deadline and self.status not in ("notified", "resolved"):
            delta = self.ncsa_deadline - timezone.now()
            return max(0, int(delta.total_seconds() / 3600))
        return None

    @property
    def is_overdue(self):
        return (
            self.ncsa_deadline
            and timezone.now() > self.ncsa_deadline
            and self.status not in ("notified", "resolved")
        )


class ErasureRequest(models.Model):
    """طلب حق المحو — PDPPL م.18"""

    STATUS = [
        ("pending", "قيد المراجعة"),
        ("approved", "تمت الموافقة"),
        ("processing", "جارٍ التنفيذ"),
        ("completed", "مكتمل"),
        ("rejected", "مرفوض"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="erasure_requests")
    student = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, related_name="erasure_requests"
    )
    requested_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, related_name="erasure_filed"
    )
    reason = models.TextField(verbose_name="سبب الطلب")
    status = models.CharField(max_length=12, choices=STATUS, default="pending")
    reviewed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="erasure_reviewed",
    )
    review_note = models.TextField(blank=True, verbose_name="ملاحظات المراجع")
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    anonymized_id = models.CharField(
        max_length=20, blank=True, verbose_name="المعرّف المجهّل", help_text="مثل: ERASED-0001"
    )
    summary = models.JSONField(null=True, blank=True, verbose_name="ملخص البيانات المحذوفة")

    class Meta:
        verbose_name = "طلب حق المحو"
        verbose_name_plural = "طلبات حق المحو"
        ordering = ["-created_at"]

    def __str__(self):
        return f"ERASURE-{str(self.id)[:8]} | {self.get_status_display()}"
