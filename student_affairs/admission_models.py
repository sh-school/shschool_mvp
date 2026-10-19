"""طلبُ التحاق طالبٍ جديد (نموذج 07، المرحلة 1) — مستقلٌّ عن حسابٍ للطالب (W-20261001-033).

يُسجَّل الطلبُ قبل أن يوجد للطالب حسابٌ: لا مفتاحَ أجنبيَّ إلزاميّاً إلى الطالب. ويُربط بالحساب عند
مرحلة «الإدخال في النظام الداخلي» فقط (`linked_student`). الرقمُ الشخصيّ للطالب ولوليّ الأمر والحالةُ
الصحّيّة بيانات حسّاسةٌ (م.8 PDPPL) فتُشفَّر في القاعدة ولا تُسجَّل في السجلّات.
مراحلُه ومستنداتُه الأحد عشر هي سلسلةُ `transfer_chain` نفسُها.
"""

from typing import Any

from django.db import models

from core.academic_calendar import default_academic_year
from core.fields import EncryptedTextField
from core.models.academic import ClassGroup
from core.models.base import AuditedModel
from core.models.school import School
from core.models.user import CustomUser


def _stage_user(related_name: str, label: str) -> Any:
    return models.ForeignKey(
        CustomUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name=related_name,
        verbose_name=label,
    )


class AdmissionApplication(AuditedModel):
    STATUS_CHOICES = [
        ("pending", "قيد الانتظار"),
        ("approved", "موافق عليه"),
        ("rejected", "مرفوض"),
        ("completed", "مكتمل"),
        ("cancelled", "ملغى"),
    ]
    LIVING_WITH_CHOICES = [
        ("both", "الأب والأم"),
        ("father", "الأب"),
        ("mother", "الأم"),
        ("relative", "أحد الأقارب"),
        ("guardian", "ولي أمر آخر"),
        ("other", "غير ذلك"),
    ]
    TRANSPORT_CHOICES = [
        ("private", "سيارة خاصة"),
        ("bus", "حافلة"),
    ]

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="admission_applications",
        verbose_name="المدرسة",
    )
    academic_year = models.CharField(
        max_length=9, default=default_academic_year, verbose_name="العام الدراسي"
    )
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
        verbose_name="الحالة",
    )

    # ── بياناتُ الطالب ──
    student_name = models.CharField(max_length=200, verbose_name="اسم الطالب")
    student_national_id = EncryptedTextField(blank=True, verbose_name="الرقم الشخصي للطالب")
    birth_date = models.DateField(null=True, blank=True, verbose_name="تاريخ الميلاد")
    nationality = models.CharField(max_length=100, blank=True, verbose_name="الجنسية")
    current_school = models.CharField(max_length=200, blank=True, verbose_name="المدرسة الحالية")
    grade = models.CharField(max_length=3, choices=ClassGroup.GRADES, verbose_name="الصف المطلوب")
    health_status = EncryptedTextField(blank=True, verbose_name="الحالة الصحية")
    living_with = models.CharField(
        max_length=10, choices=LIVING_WITH_CHOICES, blank=True, verbose_name="يعيش مع"
    )
    transport = models.CharField(
        max_length=10, choices=TRANSPORT_CHOICES, blank=True, verbose_name="وسيلة النقل"
    )
    housing_area = models.CharField(max_length=100, blank=True, verbose_name="المنطقة")
    housing_street = models.CharField(max_length=100, blank=True, verbose_name="الشارع")
    housing_house = models.CharField(max_length=50, blank=True, verbose_name="رقم المنزل")

    # ── مقدِّمُ الطلب ──
    applicant_name = models.CharField(max_length=200, verbose_name="اسم مقدِّم الطلب")
    applicant_national_id = EncryptedTextField(blank=True, verbose_name="الرقم الشخصي لمقدِّم الطلب")
    applicant_relationship = models.CharField(max_length=50, verbose_name="صلة القرابة")
    applicant_phone = models.CharField(max_length=20, verbose_name="هاتف مقدِّم الطلب")
    declaration_accepted = models.BooleanField(default=False, verbose_name="إقرارُ مقدِّم الطلب")

    # ── السلسلة: تدقيقٌ ← اعتمادٌ ← تشعيبٌ ← إدخال ──
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    documents_checked = models.JSONField(default=list, blank=True, verbose_name="المستندات المدقَّقة")
    documents_missing_reason = models.CharField(
        max_length=500, blank=True, verbose_name="سبب نقص المستندات"
    )
    reviewed_by = _stage_user("admission_reviews", "منفّذ التدقيق")
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت التدقيق")
    approved_by = _stage_user("admission_approvals", "معتمد الطلب")
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت اعتماد الطلب")
    placed_by = _stage_user("admission_placements", "منفّذ التشعيب")
    placed_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت التشعيب")
    to_class_group = models.ForeignKey(
        "core.ClassGroup",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="admission_applications",
        verbose_name="الشعبة",
    )
    entered_by = _stage_user("admission_entries", "مُدخِل البيانات")
    entered_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت الإدخال")
    #: حسابُ الطالب الذي أُنشئ عند الإدخال — فارغٌ قبل تلك المرحلة.
    linked_student = _stage_user("admission_applications", "حساب الطالب المرتبط")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "طلب التحاق"
        verbose_name_plural = "طلبات الالتحاق"
        indexes = [models.Index(fields=["school", "status"])]

    def __str__(self) -> str:
        return f"طلب التحاق — {self.student_name}"
