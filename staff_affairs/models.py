"""
staff_affairs/models.py — نماذج شؤون الموظفين
نموذجان جديدان فقط — الباقي استعلامات من نماذج موجودة
(TeacherAbsence, StaffEvaluation, TeacherSwap, CompensatorySession).
"""

from django.conf import settings
from django.db import models

from core.models.base import AuditedModel, SchoolScopedModel
from core.models.school import School
from core.models.user import CustomUser


# ═════════════════════════════════════════════════════════════════════
# أنواع الإجازات — 16 نوع وفق قانون الموارد البشرية المدنية 15/2016
# ═════════════════════════════════════════════════════════════════════

LEAVE_TYPES = [
    ("annual", "إجازة سنوية"),            # م.69 — 30-45 يوم
    ("sick", "إجازة مرضية"),              # م.71
    ("emergency", "إجازة طارئة"),          # م.70 — 7 أيام/سنة
    ("unpaid", "إجازة بدون راتب"),         # م.81
    ("maternity", "إجازة أمومة"),          # م.73 — 3-6 أشهر
    ("hajj", "إجازة حج"),                # م.74 — 20 يوم مرة واحدة
    ("marriage", "إجازة زواج"),            # م.75 — 15 يوم مرة واحدة
    ("iddah", "إجازة عدّة"),               # م.76 — 4 أشهر و10 أيام
    ("bereavement", "إجازة عزاء"),         # م.77 — 3-7 أيام
    ("training", "إجازة تدريب"),           # م.80
    ("official", "مهمة رسمية"),
    ("study", "إجازة دراسية"),            # م.79
    ("child_care", "رعاية طفل"),
    ("work_injury", "إصابة عمل"),          # م.71 — سنتان
    ("patient_companion", "مرافقة مريض"),  # م.78
    ("other", "أخرى"),
]

LEAVE_STATUS = [
    ("pending", "قيد الانتظار"),
    ("approved", "موافق عليها"),
    ("rejected", "مرفوضة"),
    ("cancelled", "ملغاة"),
]


class LeaveBalance(SchoolScopedModel):
    """رصيد الإجازات السنوي لكل موظف — وفق قانون 15/2016."""

    staff = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="leave_balances",
        verbose_name="الموظف",
    )
    academic_year = models.CharField(
        max_length=9, default=settings.CURRENT_ACADEMIC_YEAR,
        verbose_name="العام الدراسي",
    )
    leave_type = models.CharField(
        max_length=20, choices=LEAVE_TYPES, verbose_name="نوع الإجازة",
    )
    total_days = models.PositiveSmallIntegerField(
        default=0, verbose_name="إجمالي الأيام",
    )
    used_days = models.PositiveSmallIntegerField(
        default=0, verbose_name="الأيام المستخدمة",
    )

    class Meta:
        ordering = ["leave_type"]
        verbose_name = "رصيد إجازات"
        verbose_name_plural = "أرصدة الإجازات"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "staff", "academic_year", "leave_type"],
                name="unique_leave_balance",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "staff", "academic_year"]),
        ]

    @property
    def remaining_days(self):
        return max(0, self.total_days - self.used_days)

    def __str__(self):
        return f"{self.staff.full_name} — {self.get_leave_type_display()} ({self.remaining_days} يوم)"


class LeaveRequest(AuditedModel):
    """طلب إجازة مع سير عمل الموافقة — وفق قانون 15/2016."""

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="staff_leave_requests",
        verbose_name="المدرسة",
    )
    staff = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="leave_requests",
        verbose_name="الموظف",
    )
    leave_type = models.CharField(
        max_length=20, choices=LEAVE_TYPES, verbose_name="نوع الإجازة",
    )
    start_date = models.DateField(verbose_name="تاريخ البداية")
    end_date = models.DateField(verbose_name="تاريخ النهاية")
    days_count = models.PositiveSmallIntegerField(verbose_name="عدد الأيام")
    reason = models.TextField(max_length=1000, verbose_name="السبب")
    attachment = models.FileField(
        upload_to="leave_attachments/%Y/%m/", blank=True, null=True,
        verbose_name="مرفق",
    )
    status = models.CharField(
        max_length=15, choices=LEAVE_STATUS, default="pending",
        db_index=True, verbose_name="الحالة",
    )
    reviewed_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_leave_requests", verbose_name="راجعها",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ المراجعة")
    rejection_reason = models.TextField(blank=True, verbose_name="سبب الرفض")
    academic_year = models.CharField(
        max_length=9, default=settings.CURRENT_ACADEMIC_YEAR,
        verbose_name="العام الدراسي",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "طلب إجازة"
        verbose_name_plural = "طلبات الإجازات"
        indexes = [
            models.Index(fields=["school", "staff", "status"]),
            models.Index(fields=["school", "start_date", "end_date"]),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValidationError("تاريخ النهاية يجب أن يكون بعد تاريخ البداية.")

    def __str__(self):
        return f"{self.staff.full_name} — {self.get_leave_type_display()} ({self.days_count} يوم)"
