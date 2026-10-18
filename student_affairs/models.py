"""
student_affairs/models.py — نماذج شؤون الطلاب
نموذجان جديدان فقط — الباقي استعلامات من نماذج موجودة.
"""

from django.db import models

from core.academic_calendar import default_academic_year
from core.models.base import AuditedModel, SchoolScopedModel
from core.models.school import School
from core.models.user import CustomUser

# ═════════════════════════════════════════════════════════════════════
# انتقال الطالب — وفق إجراءات بوابة معارف (eduservices.edu.gov.qa)
# ═════════════════════════════════════════════════════════════════════


class StudentTransfer(AuditedModel):
    """
    سجل انتقال طالب بين المدارس — وارد أو صادر.

    الإجراءات وفق وزارة التربية والتعليم:
    - منهج مختلف: حتى نهاية يناير
    - نفس المنهج: حتى نهاية فبراير
    - إلكتروني عبر بوابة معارف + شرط الشاغر + المنطقة الجغرافية
    """

    DIRECTION_CHOICES = [
        ("in", "وارد"),
        ("out", "صادر"),
        ("internal", "داخلي (بين شعب المدرسة)"),
    ]

    STATUS_CHOICES = [
        ("pending", "قيد الانتظار"),
        ("approved", "موافق عليه"),
        ("rejected", "مرفوض"),
        ("completed", "مكتمل"),
        ("cancelled", "ملغى"),
    ]

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="student_transfers",
        verbose_name="المدرسة",
    )
    student = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="transfers",
        verbose_name="الطالب",
    )
    direction = models.CharField(
        max_length=10,
        choices=DIRECTION_CHOICES,
        verbose_name="اتجاه الانتقال",
    )
    other_school_name = models.CharField(
        max_length=200,
        verbose_name="المدرسة الأخرى",
    )
    from_grade = models.CharField(
        max_length=3,
        blank=True,
        verbose_name="الصف (من)",
    )
    to_grade = models.CharField(
        max_length=3,
        blank=True,
        verbose_name="الصف (إلى)",
    )
    #: الشعبة المنقول إليها في الانتقال الداخلي وحده (W-20261005-008) — فارغةٌ في الوارد والصادر.
    to_class_group = models.ForeignKey(
        "core.ClassGroup",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="incoming_internal_transfers",
        verbose_name="الشعبة المنقول إليها",
    )
    transfer_date = models.DateField(verbose_name="تاريخ الانتقال")
    reason = models.TextField(
        max_length=1000,
        blank=True,
        verbose_name="سبب الانتقال",
    )
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
        verbose_name="الحالة",
    )
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    academic_year = models.CharField(
        max_length=9,
        default=default_academic_year,
        verbose_name="العام الدراسي",
    )
    #: من قرّر الانتقال الداخلي (اعتماداً أو رفضاً أو إتماماً أو نقلاً مباشراً) ومتى — W-20261001-017، D-343م.
    #: هجرةُ توسيعٍ: عمودان قابلان للإلغاء، ولا يُملآن للطلبات القديمة.
    decided_by = models.ForeignKey(
        CustomUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transfer_decisions",
        verbose_name="قرّره",
    )
    decided_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت القرار")

    #: سلسلةُ نموذج 07 للوارد والصادر (W-20261001-018): المستندات المدقَّقة ومراحلُ التدقيق والاعتماد
    #: والتشعيب والإدخال بمنفّذٍ ووقت. هجرةُ توسيعٍ: أعمدةٌ قابلةٌ للإلغاء أو بقيمةٍ افتراضيّة.
    documents_checked = models.JSONField(default=list, blank=True, verbose_name="المستندات المدقَّقة")
    documents_missing_reason = models.CharField(
        max_length=500, blank=True, verbose_name="سبب نقص المستندات"
    )
    reviewed_by = models.ForeignKey(
        CustomUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transfer_reviews",
        verbose_name="منفّذ التدقيق",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت التدقيق")
    approved_by = models.ForeignKey(
        CustomUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transfer_approvals",
        verbose_name="معتمد الطلب",
    )
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت اعتماد الطلب")
    placed_by = models.ForeignKey(
        CustomUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transfer_placements",
        verbose_name="منفّذ التشعيب",
    )
    placed_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت التشعيب")
    entered_by = models.ForeignKey(
        CustomUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transfer_entries",
        verbose_name="مُدخِل البيانات",
    )
    entered_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت الإدخال")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "انتقال طالب"
        verbose_name_plural = "انتقالات الطلاب"
        indexes = [
            models.Index(fields=["school", "student", "status"]),
            models.Index(fields=["school", "direction", "status"]),
        ]

    def __str__(self):
        direction_label = {"in": "← وارد", "out": "→ صادر"}.get(self.direction, "⇄ داخلي")
        return f"{self.student.full_name} {direction_label} — {self.other_school_name}"


# ═════════════════════════════════════════════════════════════════════
# الأنشطة والإنجازات الطلابية
# ═════════════════════════════════════════════════════════════════════


class StudentActivity(SchoolScopedModel):
    """
    سجل الأنشطة اللاصفية والإنجازات والجوائز.
    يشمل: مسابقات، شهادات، أنشطة تطوعية، رياضية، ثقافية، علمية.
    """

    TYPE_CHOICES = [
        ("club", "نادٍ / جماعة"),
        ("competition", "مسابقة"),
        ("award", "جائزة / تكريم"),
        ("certificate", "شهادة"),
        ("volunteer", "عمل تطوعي"),
        ("sports", "رياضة"),
        ("cultural", "نشاط ثقافي"),
        ("scientific", "نشاط علمي"),
        ("other", "أخرى"),
    ]

    SCOPE_CHOICES = [
        ("school", "مستوى المدرسة"),
        ("district", "مستوى المنطقة"),
        ("national", "مستوى وطني"),
        ("international", "مستوى دولي"),
    ]

    student = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="activities",
        verbose_name="الطالب",
    )
    activity_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        verbose_name="نوع النشاط",
    )
    title = models.CharField(max_length=200, verbose_name="العنوان")
    description = models.TextField(
        max_length=2000,
        blank=True,
        verbose_name="الوصف",
    )
    scope = models.CharField(
        max_length=15,
        choices=SCOPE_CHOICES,
        default="school",
        verbose_name="النطاق",
    )
    date = models.DateField(verbose_name="التاريخ")
    academic_year = models.CharField(
        max_length=9,
        default=default_academic_year,
        verbose_name="العام الدراسي",
    )
    recorded_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_activities",
        verbose_name="سُجّل بواسطة",
    )
    attachment = models.FileField(
        upload_to="student_activities/%Y/%m/",
        blank=True,
        null=True,
        verbose_name="مرفق",
    )

    class Meta:
        ordering = ["-date"]
        verbose_name = "نشاط طلابي"
        verbose_name_plural = "أنشطة طلابية"
        indexes = [
            models.Index(fields=["school", "student", "activity_type"]),
            models.Index(fields=["school", "academic_year"]),
        ]

    def __str__(self):
        return f"{self.student.full_name} — {self.title}"
