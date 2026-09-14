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
# 1.1: نموذجُ حضورِ الموظّفين — وسياسةُ الشحانية (وثيقة ت/د 2027/01)
# ═════════════════════════════════════════════════════════════════════
# البند 1.1: الدوامُ الرسميّ من 7:00 صباحاً إلى 14:00 ظهراً.
# البند 2.1: متأخرٌ إن حضر بعد 7:00.
# البند 2.4: غائبٌ إن حضر بعد 9:00 دون إذن.
# البند 4.2: سقفُ الاستئذان 7 ساعات/شهر، حدٌّ أقصى ساعتان/المرة.


ATTENDANCE_STATUS_CHOICES = [
    ("present", "حاضر"),
    ("late", "متأخّر"),
    ("absent", "غائب"),
]


class StaffAttendance(SchoolScopedModel):
    """سجلُّ حضورِ الموظّفين اليوميّ — حسابُ الحالةِ تلقائياً.

    الحقول:
      - staff: الموظّف (FK)
      - date: تاريخُ اليوم
      - check_in_time: وقتُ الحضور (time)
      - check_out_time: وقتُ الانصراف (time)
      - permit_minutes: دقائقُ الاستئذانِ المقبول (محسوب من approved PermitRequests)
      - status: حالةٌ مُحسَبة (present/late/absent)

    القاعدةُ:
      - ≤7:00 → حاضر
      - 7:01 - 8:59 → متأخّر
      - ≥9:00 → غائب
    """

    staff = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="staff_attendances",
        verbose_name="الموظّف",
    )
    date = models.DateField(verbose_name="التاريخ", db_index=True)
    check_in_time = models.TimeField(null=True, blank=True, verbose_name="وقتُ الحضور")
    check_out_time = models.TimeField(null=True, blank=True, verbose_name="وقتُ الانصراف")
    permit_minutes = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="دقائقُ الاستئذانِ المقبول",
    )
    status = models.CharField(
        max_length=10,
        choices=ATTENDANCE_STATUS_CHOICES,
        db_index=True,
        verbose_name="الحالة",
    )
    notes = models.TextField(blank=True, verbose_name="ملاحظات")

    class Meta:
        ordering = ["-date"]
        verbose_name = "حضورُ موظّف"
        verbose_name_plural = "حضورُ الموظّفين"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "staff", "date"],
                name="unique_staff_attendance_per_day",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "staff", "date"]),
            models.Index(fields=["school", "date", "status"]),
        ]

    def __str__(self):
        return f"{self.staff.full_name} — {self.date} ({self.get_status_display()})"


# ═════════════════════════════════════════════════════════════════════
# 1.3: نموذجُ الاستئذان — توسيعٌ لـ LeaveRequest بساعاتٍ قصيرة
# ═════════════════════════════════════════════════════════════════════
# البند 4.1: لا يُقبل الإذنُ إلا بعد اعتمادِ الرئيسِ المباشر.
# البند 4.2: السقفُ 7 ساعات/شهر.
# البند 4.3: إذنٌ واحدٌ فقط/يوم.
# البند 4.4: حدٌّ أقصى ساعتان/مرّة.


PERMIT_REQUEST_TYPES = [
    ("late_arrival", "تأخيرٌ صباحيّ"),
    ("early_departure", "خروجٌ مبكّر"),
    ("permit", "استئذانٌ أثناء الدوام"),
]

PERMIT_REQUEST_STATUS = [
    ("pending", "قيدُ الانتظار"),
    ("approved", "مقبولٌ"),
    ("rejected", "مرفوضٌ"),
    ("cancelled", "ملغىً"),
]


class PermitRequest(AuditedModel):
    """طلبُ إذنٍ قصير الأمد (ساعات، لا أيّام).

    الحقول:
      - staff: الموظّف
      - permit_type: تأخير/خروج مبكر/استئذان
      - date: تاريخُ الإذن
      - start_time: بدايةُ الفترة (HH:MM)
      - end_time: نهايةُ الفترة (HH:MM)
      - duration_minutes: الحسابُ التلقائيّ
      - reason: سببُ الطلب
      - status: حالةُ الموافقة
      - reviewed_by: من اعتمده
      - reviewed_at: متى
      - rejection_reason: إن رُفع
      - academic_year: العام الدراسيّ (للإحصائيات)
    """

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="permit_requests",
        verbose_name="المدرسة",
    )
    staff = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="permit_requests",
        verbose_name="الموظّف",
    )
    permit_type = models.CharField(
        max_length=20,
        choices=PERMIT_REQUEST_TYPES,
        verbose_name="نوعُ الإذن",
    )
    date = models.DateField(verbose_name="التاريخ")
    start_time = models.TimeField(verbose_name="بدايةُ الفترة")
    end_time = models.TimeField(verbose_name="نهايةُ الفترة")
    duration_minutes = models.PositiveSmallIntegerField(
        editable=False,
        verbose_name="المدّةُ بالدقائق",
    )
    reason = models.TextField(max_length=1000, verbose_name="السبب")
    status = models.CharField(
        max_length=15,
        choices=PERMIT_REQUEST_STATUS,
        default="pending",
        db_index=True,
        verbose_name="الحالة",
    )
    reviewed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_permit_requests",
        verbose_name="اعتمدَهُ",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخُ الاعتماد")
    rejection_reason = models.TextField(blank=True, verbose_name="سببُ الرفض")
    academic_year = models.CharField(
        max_length=9,
        default=default_academic_year,
        verbose_name="العام الدراسيّ",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "طلبُ إذنٍ"
        verbose_name_plural = "طلباتُ الأذونات"
        constraints = [
            # لا إذنان في نفسِ اليوم
            models.UniqueConstraint(
                fields=["school", "staff", "date"],
                condition=models.Q(status="approved"),
                name="unique_approved_permit_per_day",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "staff", "status"]),
            models.Index(fields=["school", "date", "status"]),
            models.Index(fields=["school", "staff", "academic_year"]),
        ]

    def save(self, *args, **kwargs):
        """حسابُ المدّةِ التلقائيّ."""
        from datetime import datetime, timedelta

        start = datetime.combine(datetime.today(), self.start_time)
        end = datetime.combine(datetime.today(), self.end_time)
        if end <= start:
            end += timedelta(days=1)
        duration = (end - start).total_seconds() / 60
        self.duration_minutes = int(duration)
        super().save(*args, **kwargs)

    def clean(self):
        from datetime import datetime, timedelta
        from django.core.exceptions import ValidationError

        if self.end_time and self.start_time and self.end_time <= self.start_time:
            raise ValidationError("وقتُ النهايةِ يجبُ أن يكونَ بعدَ وقتِ البداية.")

        # حدٌّ أقصى ساعتان (120 دقيقة) — البند 4.4
        if self.end_time and self.start_time:
            start = datetime.combine(datetime.today(), self.start_time)
            end = datetime.combine(datetime.today(), self.end_time)
            if end <= start:
                end += timedelta(days=1)
            duration = (end - start).total_seconds() / 60
            if duration > 120:
                raise ValidationError("حدُّ الإذنِ الأقصى ساعتان (120 دقيقة) — البند 4.4.")

    def __str__(self):
        return f"{self.staff.full_name} — {self.get_permit_type_display()} ({self.date})"
