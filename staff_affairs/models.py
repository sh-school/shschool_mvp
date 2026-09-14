"""
staff_affairs/models.py — نماذج شؤون الموظفين
نموذجان جديدان فقط — الباقي استعلامات من نماذج موجودة
(TeacherAbsence, StaffEvaluation, TeacherSwap, CompensatorySession).
"""

from django.db import models

from core.academic_calendar import default_academic_year
from core.models.base import AuditedModel, SchoolScopedModel
from core.models.school import School
from core.models.user import CustomUser

# ═════════════════════════════════════════════════════════════════════
# أنواع الإجازات — 16 نوع وفق قانون الموارد البشرية المدنية 15/2016
# ═════════════════════════════════════════════════════════════════════

LEAVE_TYPES = [
    ("annual", "إجازة سنوية"),  # م.69 — 30-45 يوم
    ("sick", "إجازة مرضية"),  # م.71
    ("emergency", "إجازة طارئة"),  # م.70 — 7 أيام/سنة
    ("unpaid", "إجازة بدون راتب"),  # م.81
    ("maternity", "إجازة أمومة"),  # م.73 — 3-6 أشهر
    ("hajj", "إجازة حج"),  # م.74 — 20 يوم مرة واحدة
    ("marriage", "إجازة زواج"),  # م.75 — 15 يوم مرة واحدة
    ("iddah", "إجازة عدّة"),  # م.76 — 4 أشهر و10 أيام
    ("bereavement", "إجازة عزاء"),  # م.77 — 3-7 أيام
    ("training", "إجازة تدريب"),  # م.80
    ("official", "مهمة رسمية"),
    ("study", "إجازة دراسية"),  # م.79
    ("child_care", "رعاية طفل"),
    ("work_injury", "إصابة عمل"),  # م.71 — سنتان
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
        CustomUser,
        on_delete=models.CASCADE,
        related_name="leave_balances",
        verbose_name="الموظف",
    )
    academic_year = models.CharField(
        max_length=9,
        default=default_academic_year,
        verbose_name="العام الدراسي",
    )
    leave_type = models.CharField(
        max_length=20,
        choices=LEAVE_TYPES,
        verbose_name="نوع الإجازة",
    )
    total_days = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="إجمالي الأيام",
    )
    used_days = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="الأيام المستخدمة",
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
        return (
            f"{self.staff.full_name} — {self.get_leave_type_display()} ({self.remaining_days} يوم)"
        )


class LeaveRequest(AuditedModel):
    """طلب إجازة مع سير عمل الموافقة — وفق قانون 15/2016."""

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="staff_leave_requests",
        verbose_name="المدرسة",
    )
    staff = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="leave_requests",
        verbose_name="الموظف",
    )
    leave_type = models.CharField(
        max_length=20,
        choices=LEAVE_TYPES,
        verbose_name="نوع الإجازة",
    )
    start_date = models.DateField(verbose_name="تاريخ البداية")
    end_date = models.DateField(verbose_name="تاريخ النهاية")
    days_count = models.PositiveSmallIntegerField(verbose_name="عدد الأيام")
    reason = models.TextField(max_length=1000, verbose_name="السبب")
    attachment = models.FileField(
        upload_to="leave_attachments/%Y/%m/",
        blank=True,
        null=True,
        verbose_name="مرفق",
    )
    status = models.CharField(
        max_length=15,
        choices=LEAVE_STATUS,
        default="pending",
        db_index=True,
        verbose_name="الحالة",
    )
    reviewed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_leave_requests",
        verbose_name="راجعها",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ المراجعة")
    rejection_reason = models.TextField(blank=True, verbose_name="سبب الرفض")
    academic_year = models.CharField(
        max_length=9,
        default=default_academic_year,
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


# ═════════════════════════════════════════════════════════════════════
# حضورُ الموظّفين (1.1) والأذوناتُ القصيرة (1.3)
# ═════════════════════════════════════════════════════════════════════
# المرجع: AAdocs/ministry_data/2026_2027/06_attendance_performance_review.md §1
# («سياسة وضوابط الحضور والانصراف»، ت/د: 2027/01 بتاريخ 2026-08-23، مدرسة الشحانية)
# و07_forms_catalog.md جدول 1 بند 02 (نموذج طلب تأخير / استئذان / خروج مبكر).
# والقواعدُ نفسُها (الحدود والتصنيف) في `staff_affairs/attendance.py` لا هنا.

STAFF_ATTENDANCE_STATUS = [
    ("present", "حاضر"),
    ("late", "متأخّر"),
    ("absent", "غائب"),
    ("permitted", "مستأذن"),
]


class StaffAttendance(AuditedModel):
    """سجلُّ حضور موظّفٍ في يوم — «يحسب ولا ينفّذ آليّاً».

    يُسجَّل الحالُ ودقائقُ التأخّر ودقائقُ الإذن المعتمد، ولا يُخصم شيءٌ آليّاً:
    الخصمُ (البند 5) قرارٌ إداريٌّ يُبنى على التقرير الشهريّ لا على هذا الجدول.
    و``created_by``/``updated_by`` من يدِ من رصد — والتدقيقُ في ``AuditLog``.
    """

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="staff_attendance_records",
        verbose_name="المدرسة",
    )
    staff = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="staff_attendance_records",
        verbose_name="الموظف",
    )
    date = models.DateField(verbose_name="التاريخ")
    status = models.CharField(max_length=10, choices=STAFF_ATTENDANCE_STATUS, verbose_name="الحالة")
    check_in = models.TimeField(null=True, blank=True, verbose_name="وقت الحضور")
    check_out = models.TimeField(null=True, blank=True, verbose_name="وقت الانصراف")
    late_minutes = models.PositiveSmallIntegerField(default=0, verbose_name="دقائق التأخّر")
    permit_minutes = models.PositiveSmallIntegerField(default=0, verbose_name="دقائق الإذن المعتمد")
    notes = models.CharField(max_length=300, blank=True, verbose_name="ملاحظات")

    class Meta:
        ordering = ["-date"]
        verbose_name = "حضور موظف"
        verbose_name_plural = "حضور الموظفين"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "staff", "date"], name="unique_staff_attendance_day"
            ),
        ]
        indexes = [
            models.Index(fields=["school", "date", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.staff.full_name} — {self.date} ({self.get_status_display()})"


PERMIT_TYPES = [
    ("late_arrival", "تأخير صباحي"),
    ("during_day", "استئذان أثناء الدوام"),
    ("early_departure", "خروج مبكر"),
]

PERMIT_STATUS = [
    ("pending", "قيد الانتظار"),
    ("approved", "معتمد"),
    ("rejected", "مرفوض"),
    ("cancelled", "ملغى"),
]


class PermitRequest(AuditedModel):
    """طلبُ إذنٍ قصير: تأخيرٌ صباحيّ أو استئذانٌ أثناء الدوام أو خروجٌ مبكر (نموذج 02).

    **لماذا نموذجٌ مستقلٌّ لا توسيعُ ``LeaveRequest``:** الإجازةُ تُعدّ بالأيّام
    (``start_date``/``end_date``/``days_count``) ويُخصم رصيدُها السنويُّ من
    ``LeaveBalance`` بنوعها، ولها ستّةَ عشرَ نوعاً من قانون 15/2016. والإذنُ يُعدّ
    بالدقائق داخل يومٍ واحد (من الساعة – إلى الساعة)، وسقفُه شهريّ (7 ساعات،
    البند 4.2) لا سنويّ، وحدُّه ساعتان للمرّة (4.4) ومرّةٌ في اليوم (4.3). فتوسيعُ
    ``LeaveRequest`` كان سيجعل نصفَ حقوله فارغاً في كلّ صفّ، ويخلط رصيدين
    بوحدتين مختلفتين في جدولٍ واحد.

    والرصيدُ لا يُخزَّن: يُجمع من الأذونات المعتمدة في الشهر (``PermitService``).
    """

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="staff_permit_requests",
        verbose_name="المدرسة",
    )
    staff = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="permit_requests",
        verbose_name="الموظف",
    )
    permit_type = models.CharField(max_length=20, choices=PERMIT_TYPES, verbose_name="نوع الطلب")
    date = models.DateField(verbose_name="التاريخ")
    start_time = models.TimeField(verbose_name="من الساعة")
    end_time = models.TimeField(verbose_name="إلى الساعة")
    duration_minutes = models.PositiveSmallIntegerField(verbose_name="المدة بالدقائق")
    reason = models.CharField(max_length=500, verbose_name="سبب الطلب")
    status = models.CharField(
        max_length=10, choices=PERMIT_STATUS, default="pending", verbose_name="الحالة"
    )
    reviewed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_permit_requests",
        verbose_name="اعتمده",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ المراجعة")
    rejection_reason = models.CharField(max_length=300, blank=True, verbose_name="سبب الرفض")

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "طلب إذن"
        verbose_name_plural = "طلبات الأذونات"
        constraints = [
            # البند 4.3: «لا يجوز الإذن أكثر من مرة واحدة في اليوم الواحد».
            models.UniqueConstraint(
                fields=["school", "staff", "date"],
                condition=models.Q(status="approved"),
                name="one_approved_permit_per_day",
            ),
            # django-stubs 5.0.2 لا يعرف `condition` (Django 5.1).
            models.CheckConstraint(  # type: ignore[call-arg]
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="permit_end_after_start",
            ),
            # البند 4.4: «الحد الأقصى للإذن ساعتين في المرة الواحدة».
            # django-stubs 5.0.2 لا يعرف `condition` (Django 5.1).
            models.CheckConstraint(  # type: ignore[call-arg]
                condition=models.Q(duration_minutes__gt=0, duration_minutes__lte=120),
                name="permit_duration_within_two_hours",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "staff", "date"]),
            models.Index(fields=["school", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.staff.full_name} — {self.get_permit_type_display()} ({self.date})"
