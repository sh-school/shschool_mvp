"""
student_affairs/models.py — نماذج شؤون الطلاب
نموذجان جديدان فقط — الباقي استعلامات من نماذج موجودة.
"""

import uuid

from django.conf import settings
from django.db import models

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
    ]

    STATUS_CHOICES = [
        ("pending", "قيد الانتظار"),
        ("approved", "موافق عليه"),
        ("rejected", "مرفوض"),
        ("completed", "مكتمل"),
        ("cancelled", "ملغى"),
    ]

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="student_transfers",
        verbose_name="المدرسة",
    )
    student = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="transfers",
        verbose_name="الطالب",
    )
    direction = models.CharField(
        max_length=3, choices=DIRECTION_CHOICES, verbose_name="اتجاه الانتقال",
    )
    other_school_name = models.CharField(
        max_length=200, verbose_name="المدرسة الأخرى",
    )
    from_grade = models.CharField(
        max_length=3, blank=True, verbose_name="الصف (من)",
    )
    to_grade = models.CharField(
        max_length=3, blank=True, verbose_name="الصف (إلى)",
    )
    transfer_date = models.DateField(verbose_name="تاريخ الانتقال")
    reason = models.TextField(
        max_length=1000, blank=True, verbose_name="سبب الانتقال",
    )
    status = models.CharField(
        max_length=15, choices=STATUS_CHOICES, default="pending",
        db_index=True, verbose_name="الحالة",
    )
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    academic_year = models.CharField(
        max_length=9, default=settings.CURRENT_ACADEMIC_YEAR,
        verbose_name="العام الدراسي",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "انتقال طالب"
        verbose_name_plural = "انتقالات الطلاب"
        indexes = [
            models.Index(fields=["school", "student", "status"]),
            models.Index(fields=["school", "direction", "status"]),
        ]

    def __str__(self):
        direction_label = "← وارد" if self.direction == "in" else "→ صادر"
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
        CustomUser, on_delete=models.CASCADE, related_name="activities",
        verbose_name="الطالب",
    )
    activity_type = models.CharField(
        max_length=20, choices=TYPE_CHOICES, verbose_name="نوع النشاط",
    )
    title = models.CharField(max_length=200, verbose_name="العنوان")
    description = models.TextField(
        max_length=2000, blank=True, verbose_name="الوصف",
    )
    scope = models.CharField(
        max_length=15, choices=SCOPE_CHOICES, default="school",
        verbose_name="النطاق",
    )
    date = models.DateField(verbose_name="التاريخ")
    academic_year = models.CharField(
        max_length=9, default=settings.CURRENT_ACADEMIC_YEAR,
        verbose_name="العام الدراسي",
    )
    recorded_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="recorded_activities", verbose_name="سُجّل بواسطة",
    )
    attachment = models.FileField(
        upload_to="student_activities/%Y/%m/", blank=True, null=True,
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
