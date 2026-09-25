from datetime import timedelta
from typing import Any

from django.core.exceptions import PermissionDenied
from django.db import models
from django.utils import timezone

from .school import School, _uuid
from .user import CustomUser


class _ImmutableQuerySet(models.QuerySet):
    """يمنع الحذفَ والتعديلَ الجماعيَّ — PDPPL م.19.

    ويُستثنى فصلُ هويّةِ الفاعل وحدَه (`user=None`): من مُحي حسابُه تُفصَل
    هويّتُه عن السجلّ (م.15) وتبقى الواقعةُ بتفاصيلها. وهو ما يفعله Django
    نفسُه قبل حذف مستخدم، فبلا هذا الاستثناء يستحيل محوُ أيّ حساب.
    """

    def delete(self):
        raise PermissionDenied("AuditLog records are immutable and cannot be deleted.")

    def update(self, **kwargs):
        if set(kwargs) == {"user"} and kwargs["user"] is None:
            return super().update(**kwargs)
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
        # الفشلُ يُدقَّق كالنجاح: عشرُ محاولاتٍ خاطئةٍ على حسابٍ واحدٍ في دقيقةٍ
        # هجومٌ يُرى في السجلّ لا في ذاكرة الخادم وحدَها.
        ("login_failed", "محاولة دخول فاشلة"),
        ("mfa_failed", "رمز تحقّق خاطئ"),
    ]
    MODEL_CHOICES = [
        ("HealthRecord", "سجل صحي"),
        ("BehaviorInfraction", "مخالفة سلوكية"),
        ("StudentSubjectResult", "درجة طالب"),
        ("ClinicVisit", "زيارة عيادة"),
        ("CustomUser", "مستخدم"),
        ("Membership", "عضويّة كادر"),
        ("ParentStudentLink", "ربط ولي أمر"),
        ("BookBorrowing", "إعارة كتاب"),
        ("ConsentRecord", "سجل موافقة"),
        ("StudentAssessmentGrade", "درجة تقييم"),
        ("StaffEvaluation", "تقييم أداء موظف"),
        ("other", "أخرى"),
    ]

    objects = _ImmutableManager()

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="audit_logs",
        verbose_name="المدرسة",
    )
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_actions",
        verbose_name="المستخدم",
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, verbose_name="الإجراء")
    model_name = models.CharField(
        max_length=50, choices=MODEL_CHOICES, default="other", verbose_name="النموذج"
    )
    object_id = models.CharField(max_length=100, blank=True, verbose_name="معرّف السجل")
    object_repr = models.CharField(max_length=300, blank=True, verbose_name="وصف السجل")
    changes = models.JSONField(null=True, blank=True, verbose_name="التغييرات")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="عنوان IP")
    user_agent = models.CharField(max_length=300, blank=True, verbose_name="المتصفّح")
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="الوقت")

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

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk and AuditLog.objects.filter(pk=self.pk).exists():
            raise PermissionDenied("AuditLog records are immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("AuditLog records are immutable and cannot be deleted.")

    @classmethod
    def log(
        cls,
        *,
        user: Any,
        action: str,
        model_name: str,
        object_id: Any = "",
        object_repr: Any = "",
        changes: Any = None,
        school: Any = None,
        request: Any = None,
    ) -> None:
        ip = ua = ""
        if request:
            from core.request_utils import get_client_ip

            ip = get_client_ip(request)  # IP الحقيقي خلف وكيل Railway (لا IP الوكيل)
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
    school = models.ForeignKey(School, on_delete=models.CASCADE, verbose_name="المدرسة")
    parent = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="consent_records",
        verbose_name="وليّ الأمر",
    )
    student = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="consent_as_student",
        verbose_name="الطالب",
    )
    data_type = models.CharField(max_length=20, choices=DATA_TYPES, verbose_name="نوع البيانات")
    is_given = models.BooleanField(default=True, verbose_name="تمت الموافقة")
    method = models.CharField(
        max_length=10, choices=METHODS, default="digital", verbose_name="طريقة الموافقة"
    )
    given_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الموافقة")
    withdrawn_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ السحب")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    recorded_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="consents_recorded",
        verbose_name="سجّله",
    )

    class Meta:
        verbose_name = "سجل موافقة"
        verbose_name_plural = "سجلات الموافقة"
        ordering = ["-given_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "student", "data_type"],
                name="unique_consent_record",
            ),
        ]

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
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="breach_reports", verbose_name="المدرسة"
    )
    title = models.CharField(max_length=300, verbose_name="عنوان الخرق")
    description = models.TextField(verbose_name="وصف الخرق التفصيلي")
    severity = models.CharField(
        max_length=10, choices=SEVERITY, default="medium", verbose_name="الخطورة"
    )
    data_type_affected = models.CharField(
        max_length=15,
        choices=DATA_TYPES_AFFECTED,
        default="personal",
        verbose_name="نوع البيانات المتأثرة",
    )
    affected_count = models.PositiveIntegerField(default=0, verbose_name="عدد الأشخاص المتأثرين")
    discovered_at = models.DateTimeField(verbose_name="وقت الاكتشاف")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    ncsa_deadline = models.DateTimeField(
        null=True, blank=True, verbose_name="موعد إشعار NCSA (72 ساعة)"
    )
    ncsa_notified_at = models.DateTimeField(
        null=True, blank=True, verbose_name="وقت إشعار NCSA الفعلي"
    )
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ المعالجة")
    status = models.CharField(
        max_length=15, choices=STATUS, default="discovered", verbose_name="الحالة"
    )
    reported_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="reported_breaches",
        verbose_name="المُبلِّغ",
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
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="erasure_requests", verbose_name="المدرسة"
    )
    student = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="erasure_requests",
        verbose_name="الطالب",
    )
    requested_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="erasure_filed",
        verbose_name="مقدّم الطلب",
    )
    reason = models.TextField(verbose_name="سبب الطلب")
    status = models.CharField(
        max_length=12, choices=STATUS, default="pending", verbose_name="الحالة"
    )
    reviewed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="erasure_reviewed",
        verbose_name="راجعه",
    )
    review_note = models.TextField(blank=True, verbose_name="ملاحظات المراجع")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ المراجعة")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الاكتمال")
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
