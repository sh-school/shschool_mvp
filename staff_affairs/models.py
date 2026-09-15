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

#: أنواعُ يوم الغياب كما في سجلّ الغياب المدرسيّ نفسِه — «07-نماذج المدرسة/08) سجل
#: الغياب.xlsx»، قائمةُ التحقّق في خلايا الأيّام (E3:X122) وأعمدةُ «الإحصائية الشهرية».
#: والغيابُ بلا نوعٍ غيابٌ لم يُغطَّ بعد — «يجب على الموظف تغطية أيام غيابه قبل يوم (15)
#: من الشهر وإلا يتم تنفيذ الخصم» (البند 5.3، 06:69).
ABSENCE_TYPES = [
    ("casual", "عارضة"),
    ("unpaid", "بدون راتب"),
    ("sick", "مرضية"),
    ("official_mission", "مهمة رسمية"),
    ("experience_exchange", "تبادل خبرات"),
    ("external_training", "تدريب خارجي"),
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
    #: البند 1.1: الدوامُ «ينتهي في تمام الثانية ظهراً» — ما بين الانصراف و14:00 بلا إذن.
    early_leave_minutes = models.PositiveSmallIntegerField(
        default=0, verbose_name="دقائق الانصراف المبكر بلا إذن"
    )
    #: نوعُ يوم الغياب (سجلّ الغياب المدرسيّ)، والفارغُ غيابٌ لم يُغطَّ (5.3).
    absence_type = models.CharField(
        max_length=20, choices=ABSENCE_TYPES, blank=True, verbose_name="نوع الغياب"
    )
    #: البند 2.4 «دون إذن أو عذر مقبول» — العذرُ الذي قُبل فعُدّ الحضورُ بعد 9:00 تأخّراً.
    accepted_excuse = models.CharField(
        max_length=300, blank=True, verbose_name="العذر المقبول (البند 2.4)"
    )
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

#: مراحلُ نموذج 02 بترتيبها — 07_forms_catalog.md:13 و07b_forms_catalog_thirdpass.md:13:
#: «المسؤول المباشر ← النائب المسؤول ← السكرتارية (تسجّل رصيد الساعات) ← الإدارة».
#: وفي أصل PDF (07-نماذج المدرسة/02، ص1) تحت «استخدام المسؤول المباشر والنائب المسؤول»
#: عمودان منفصلان لكلٍّ منهما موافق/غير موافق والاسم والتوقيع — فهما مرحلتان. ومن لا
#: مسؤولَ مباشراً له غيرَ نائبه يبدأ طلبُه بمربّع النائب (``direct_manager``).
#: و«external» لإذن المدير نفسِه: يعتمده رئيسُه خارج المدرسة، وتُثبته السكرتارية بمرجعه.
PERMIT_STAGES = [
    ("supervisor", "المسؤول المباشر"),
    ("deputy", "النائب المسؤول"),
    ("secretary", "السكرتارية"),
    ("principal", "مدير المدرسة"),
    ("external", "اعتماد رئيس المدير"),
    ("closed", "مغلق"),
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

    والمراحلُ مراحلُ النموذج (``PERMIT_STAGES``): توقيعُ المسؤول المباشر، ثمّ
    السكرتاريةُ تسجّل رصيدَ الساعات واسمَها ووقتَ تسجيلها (07b:13)، ثمّ اعتمادُ
    مدير المدرسة — «ولا يخرج الموظف فعلياً إلا بعد اعتماد مدير المدرسة» (07:13).
    والرصيدُ لا يُخزَّن حيّاً: يُجمع من الأذونات المعتمدة في الشهر (``PermitService``)،
    وما تسجّله السكرتاريةُ لقطةٌ لما رأته يومَ سجّلت.
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
    stage = models.CharField(
        max_length=10, choices=PERMIT_STAGES, default="supervisor", verbose_name="المرحلة"
    )
    #: المسؤولُ المباشرُ يومَ التقديم حين يكون غيرَ النائب (منسّقُ قسم المعلّم) — لقطة.
    line_manager = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="line_managed_permit_requests",
        verbose_name="المسؤول المباشر المسمّى",
    )
    #: دورُ «النائب المسؤول» يومَ التقديم (rbac_roles.json «reports_to») — لقطةٌ لا تتبدّل
    #: بتبدّل دور الموظّف بعده. والفارغُ طلبُ مدير المدرسة نفسِه.
    deputy_role = models.CharField(max_length=30, blank=True, verbose_name="دور النائب المسؤول")
    supervisor_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supervised_permit_requests",
        verbose_name="المسؤول المباشر",
    )
    supervisor_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت موافقة المسؤول")
    deputy_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deputy_permit_requests",
        verbose_name="النائب المسؤول",
    )
    deputy_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت موافقة النائب")
    secretary_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_permit_requests",
        verbose_name="موظف السكرتارية",
    )
    secretary_at = models.DateTimeField(null=True, blank=True, verbose_name="توقيت تسجيل الرصيد")
    #: «رصيد الساعات» في مربّع السكرتارية (07b:13): المتبقّي من السقف الشهريّ قبل هذا الطلب.
    recorded_balance_minutes = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="رصيد الساعات المسجّل (دقائق)"
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
    rejected_stage = models.CharField(
        max_length=10, choices=PERMIT_STAGES, blank=True, verbose_name="مرحلة الرفض"
    )
    #: مرجعُ قرار رئيس المدير في إذن المدير نفسِه (بريدٌ أو كتابٌ وتاريخُه).
    external_reference = models.CharField(
        max_length=300, blank=True, verbose_name="مرجع اعتماد رئيس المدير"
    )

    @property
    def is_principals_own(self) -> bool:
        """طلبُ مدير المدرسة نفسِه — لا نائبَ مسؤولاً فوقه (``deputy_role`` فارغ)."""
        return not self.deputy_role

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "طلب إذن"
        verbose_name_plural = "طلبات الأذونات"
        constraints = [
            # البند 4.3 (06_attendance_performance_review.md:58):
            # «لا يجوز الإذن أكثر من مرة واحدة في اليوم الواحد».
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
            # البند 4.4 (06_attendance_performance_review.md:59):
            # «يكون الحد الأقصى للإذن ساعتين في المرة الواحدة».
            # django-stubs 5.0.2 لا يعرف `condition` (Django 5.1).
            models.CheckConstraint(  # type: ignore[call-arg]
                condition=models.Q(duration_minutes__gt=0, duration_minutes__lte=120),
                name="permit_duration_within_two_hours",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "staff", "date"]),
            models.Index(fields=["school", "status", "stage"]),
        ]

    def __str__(self) -> str:
        return f"{self.staff.full_name} — {self.get_permit_type_display()} ({self.date})"


#: نموذج 03 (07_forms_catalog.md:14، وأصلُه «07-نماذج المدرسة/03) نموذج طلب.pdf» ص1):
#: «يجب ارفاق مع طلب استثناء الخروج المبكر أو التأخير الصباحي ما يثبت حاجة الموظف لذلك».
EXCEPTION_TYPES = [
    ("late_arrival", "تأخير صباحي"),
    ("early_departure", "خروج مبكر"),
]

EXCEPTION_STATUS = [
    ("pending", "قيد الانتظار"),
    ("approved", "معتمد"),
    ("rejected", "مرفوض"),
]


class AttendanceException(AuditedModel):
    """استثناءٌ من ساعة الحضور أو الانصراف لأيّامٍ متتالية — نموذج 03 بقرار المدير.

    **لماذا لا يُحمل على ``PermitRequest``:** الإذنُ يومٌ واحدٌ بساعتين أقصاه ومرّةٌ في
    اليوم وسبعُ ساعاتٍ في الشهر (4.2–4.4)، ويمرّ بأربعة مربّعات. والاستثناءُ مدّةٌ من
    الأيّام بساعةٍ ثابتة، يقرّره المديرُ وحدَه («استخدام مدير المدرسة») على ما يثبت الحاجة،
    ولا تحدّه قيودُ الأذونات. فجمعُهما كان سيُسقط القيود أو يفرضها على ما لا تنطبق عليه.
    """

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="staff_attendance_exceptions",
        verbose_name="المدرسة",
    )
    staff = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="attendance_exceptions",
        verbose_name="الموظف",
    )
    exception_type = models.CharField(
        max_length=20, choices=EXCEPTION_TYPES, verbose_name="نوع الاستثناء"
    )
    start_date = models.DateField(verbose_name="من تاريخ")
    end_date = models.DateField(verbose_name="إلى تاريخ")
    #: التأخيرُ: الحضورُ حتّى هذه الساعة؛ والخروجُ المبكر: الانصرافُ من هذه الساعة.
    boundary_time = models.TimeField(verbose_name="الساعة")
    content = models.CharField(max_length=1000, verbose_name="محتوى الطلب")
    #: «ما يثبت حاجة الموظف» — وصفُ المرفق، والأصلُ لدى الإدارة.
    evidence = models.CharField(max_length=300, verbose_name="ما يثبت الحاجة")
    status = models.CharField(
        max_length=10, choices=EXCEPTION_STATUS, default="pending", verbose_name="الحالة"
    )
    feedback = models.CharField(max_length=500, blank=True, verbose_name="التغذية الراجعة")
    reviewed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_attendance_exceptions",
        verbose_name="قرّره",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ التغذية الراجعة")

    class Meta:
        ordering = ["-start_date", "-created_at"]
        verbose_name = "استثناء حضور (نموذج 03)"
        verbose_name_plural = "استثناءات الحضور (نموذج 03)"
        constraints = [
            models.CheckConstraint(  # type: ignore[call-arg]
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="attendance_exception_dates_ordered",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "staff", "status", "start_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.staff.full_name} — {self.get_exception_type_display()} ({self.start_date})"


class PrincipalDelegation(AuditedModel):
    """إنابةُ نائب الشؤون الإدارية عن المدير ليومٍ — بقرار المدير نفسه.

    03_job_descriptions_rbac.md:401 «الإنابة عن المدير في مهامه في حال غيابه». ويُكتب
    القرارُ هنا بيد المدير، فلا تنتقل صلاحيةُ الاعتماد النهائيّ بغير علمه.
    """

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="principal_delegations",
        verbose_name="المدرسة",
    )
    date = models.DateField(verbose_name="اليوم")
    delegate = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="principal_delegations",
        verbose_name="النائب المُناب",
    )

    class Meta:
        ordering = ["-date"]
        verbose_name = "إنابة عن المدير"
        verbose_name_plural = "الإنابات عن المدير"
        constraints = [
            models.UniqueConstraint(fields=["school", "date"], name="one_delegation_per_day"),
        ]

    def __str__(self) -> str:
        return f"{self.date} — {self.delegate.full_name}"
