"""
staff_affairs/models.py — نماذج شؤون الموظفين
نموذجان جديدان فقط — الباقي استعلامات من نماذج موجودة
(TeacherAbsence, TeacherSwap, CompensatorySession). وتقييمُ الأداء في `quality.EmployeeEvaluation`
(ADR-0002) — لا في `StaffEvaluation` المُهمَل.
"""

from django.db import models

from core.academic_calendar import default_academic_year
from core.models.base import AuditedModel, SchoolScopedModel
from core.models.school import School
from core.models.user import CustomUser

# ═════════════════════════════════════════════════════════════════════
# أنواع الإجازات — 16 نوع وفق قانون الموارد البشرية المدنية 15/2016
# ═════════════════════════════════════════════════════════════════════

#: أنواعُ الإجازات ومددُها من قانون الموارد البشرية 15/2016 المعدَّل بقانون 25/2025 (المادّة 61)
#: ولائحته التنفيذية 32/2016 المعدَّلة بقرار 34/2025 — نصوصُها الحرفيّة في
#: ``AAdocs/ministry_data/2026_2027/02d_hr_law_leaves_verbatim.md``. وموظفو المدارس يسري
#: عليهم القانونُ فيما لم يرد فيه نصٌّ خاصّ في النظام الوظيفيّ (قرار 32/2019، م-2 من
#: القرار)، وللنظام الوظيفيّ ثلاثُ موادّ في الإجازات (24 و25 و26) تتقدّم حيث تخالف.
LEAVE_TYPES = [
    # قانون م.62: 45/40/30 يوماً بحسب الدرجة؛ ولموظفي المدارس الصيفيّة وفق التقويم (نظام م-24)
    ("annual", "إجازة سنوية"),
    # قانون م.66 وم.69: ≤3 أيام متصلة و15 يوماً/سنة بترخيص الجهة الطبية، وما زاد باعتمادها
    ("sick", "إجازة مرضية"),
    # العارضة — قانون م.65: 10 أيام عمل/سنة تسقط بانقضاء السنة المالية؛ ولائحة م.81 في الإخطار
    ("emergency", "إجازة عارضة"),
    # قانون م.61(17)؛ ولائحة م.92: ≤شهر بقرار الرئيس التنفيذي
    ("unpaid", "إجازة بدون راتب"),
    # قانون م.73: 3 أشهر (6 للتوائم/ذي إعاقة)؛ نظام المدارس م-25: شهران (3 للتوائم)
    ("maternity", "إجازة أمومة"),
    # قانون م.75: 21 يوماً مرة واحدة للمسلم
    ("hajj", "إجازة حج"),
    # قانون م.76: 15 يوماً
    ("marriage", "إجازة زواج"),
    # قانون م.77: 4 أشهر و10 أيام
    ("iddah", "إجازة عدّة"),
    # لائحة م.84: 5 أيام (قريب درجة أولى) أو 3 (حتى الرابعة) أو 7 مع السفر
    ("bereavement", "إجازة عزاء"),
    # قانون م.77 مكرراً: تفرّغ ≤15 يوماً/شهر و≤شهرين/سنة
    ("training", "إجازة تدريب"),
    # لائحة م.23–28: إيفاد بقرار الرئيس
    ("official", "مهمة رسمية"),
    # قانون م.77 مكرراً/1؛ ولائحة م.91 لإجازة الامتحانات
    ("study", "إجازة دراسية"),
    # قانون م.74 (القطرية، أبناء ذوو إعاقة، ≤5 سنوات)؛ ولائحة م.88
    ("child_care", "رعاية طفل"),
    # قانون م.71: ≤سنتين لا تُحسب من الدورية والمرضية
    ("work_injury", "إصابة عمل"),
    # لائحة م.87؛ ونظام المدارس م-26 للعلاج بالخارج
    ("patient_companion", "مرافقة مريض"),
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
# والقواعدُ نفسُها (الحدود والتصنيف) في `staff_affairs/attendance/` (حزمة) لا هنا.

STAFF_ATTENDANCE_STATUS = [
    ("present", "حاضر"),
    ("late", "متأخّر"),
    ("absent", "غائب"),
    ("permitted", "مستأذن"),
]

#: أنواعُ يوم الغياب كما في سجلّ الغياب المدرسيّ نفسِه — «07-نماذج المدرسة/08) سجل
#: الغياب.xlsx»، قائمةُ التحقّق في خلايا الأيّام (E3:X122) وأعمدةُ «الإحصائية الشهرية».
#: والغيابُ بلا نوعٍ غيابٌ لم يُغطَّ بعد — «يجب على الموظف تغطية أيام غيابه قبل يوم (15)
#: من الشهر وإلا يتم تنفيذ الخصم» (البند 5.3)؛ والتغطيةُ بعد المهلة تُسجَّل وتُوسم
#: ولا تُمنع (م-35).
ABSENCE_TYPES = [
    ("casual", "عارضة"),
    ("unpaid", "بدون راتب"),
    ("sick", "مرضية"),
    ("official_mission", "مهمة رسمية"),
    ("experience_exchange", "تبادل خبرات"),
    ("external_training", "تدريب خارجي"),
    # أنواعُ إجازات القانون واللائحة التي ليست في سجلّ الغياب المدرسيّ 08 — قرارُ المالك
    # 2026-09-19: «حسب اللوائح: عارضة، مرضية، عاطفية (عزاء) …» (02d، قانون م.61 ولائحة م.84).
    ("bereavement", "عزاء"),
    ("marriage", "زواج"),
    ("hajj", "حج"),
    ("maternity", "وضع"),
    ("iddah", "عدّة شرعية"),
    ("patient_companion", "مرافقة مريض"),
    ("work_injury", "إصابة عمل"),
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
    #: البند 2.4 «دون إذن أو عذر مقبول» — العذرُ الذي قُبل فعُدّ الحضورُ بعد 9:00 تأخّراً،
    #: ولا يقبله إلّا المديرُ أو من ينوب عنه (م-7). ونصُّه هنا وحدَه لا في سجلّ التدقيق.
    accepted_excuse = models.CharField(
        max_length=300, blank=True, verbose_name="العذر المقبول (البند 2.4)"
    )
    #: م-7: «ويُسجَّل مع العذر سببُه ومن قبله ووقتُ القبول».
    excuse_accepted_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accepted_staff_excuses",
        verbose_name="قبِل العذر",
    )
    excuse_accepted_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت قبول العذر")
    #: م-25: قبولٌ بيد نائب الشؤون الإدارية بالإنابة عن المدير — يُوسم.
    excuse_on_behalf = models.BooleanField(default=False, verbose_name="قُبل العذر بالإنابة")
    #: م-35: وقتُ أوّلِ تغطيةٍ لغياب هذا اليوم (نوعٌ من سجلّ الغياب، أو عذرٌ أو استثناءٌ
    #: رفع التصنيف). والمهلةُ «قبل يوم (15) من الشهر» (البند 5.3) — وما بعدها يُوسم في
    #: التقرير ولا يُمنع.
    covered_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت تغطية الغياب")
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
    # م-18ب: استئذانٌ أو خروجٌ مبكرٌ مضى وقتُ بدئه ولم يُعتمد — «لا يعتبر الطلب معتمداً
    # الا باعتماد مدير المدرسة» (حاشية نموذج 02)، فلا يُعتمد بعد وقته ولا يبقى معلّقاً.
    ("expired", "منتهٍ"),
]

#: مراحلُ نموذج 02 بترتيب مربّعات الورقة نفسِها (م-19 من
#: ``docs/compliance/staff_attendance_spec.md``، و[ن02] ص1): بيانات الموظّف، ثمّ
#: «استخدام السكرتارية» (رصيد الساعات، الاسم، توقيت تقديم)، ثمّ «استخدام المسؤول
#: المباشر والنائب المسؤول» في عمودين، ثمّ «استخدام الإدارة» و«مدير المدرسة». وما كان
#: في كتالوج النماذج (مباشر ← نائب ← سكرتارية ← إدارة) ترتيبُ نموذج 01 نُسخ خطأً (ز-1).
#: والعمودان خطوةٌ واحدةٌ بتوقيعٍ واحد لأنّ صاحبَهما واحد (م-19، م-21) — فلا مرحلةَ
#: «deputy» مستقلّة (ز-8). و«principal» هي «استخدام الإدارة» ومربّعُ المدير معاً (س-2).
#: و«external» لإذن المدير نفسِه: قرارٌ من خارج المدرسة تُثبته السكرتارية بمرجعه (م-23).
PERMIT_STAGES = [
    ("secretary", "السكرتارية"),
    ("coordinator", "منسّق المادّة"),
    ("supervisor", "المسؤول المباشر والنائب المسؤول"),
    ("principal", "مدير المدرسة"),
    ("external", "اعتماد خارجي"),
    ("closed", "مغلق"),
]


class PermitRequest(AuditedModel):
    """طلبُ إذنٍ قصير: تأخيرٌ صباحيّ أو استئذانٌ أثناء الدوام أو خروجٌ مبكر (نموذج 02).

    **لماذا نموذجٌ مستقلٌّ لا توسيعُ ``LeaveRequest``:** الإجازةُ تُعدّ بالأيّام
    (``start_date``/``end_date``/``days_count``) ويُخصم رصيدُها السنويُّ من
    ``LeaveBalance`` بنوعها، ولها ستّةَ عشرَ نوعاً من قانون 15/2016. والإذنُ يُعدّ
    بالدقائق داخل يومٍ واحد (من الساعة – إلى الساعة)، وسقفُه شهريّ (10 ساعات،
    م.79/3 من قانون 15/2016) لا سنويّ، وحدُّه ثلاثُ ساعاتٍ للمرّة ومرّةٌ في اليوم (4.3). فتوسيعُ
    ``LeaveRequest`` كان سيجعل نصفَ حقوله فارغاً في كلّ صفّ، ويخلط رصيدين
    بوحدتين مختلفتين في جدولٍ واحد.

    والمراحلُ مراحلُ الورقة (``PERMIT_STAGES``، م-19): السكرتاريةُ تُثبت رصيدَ
    الساعات واسمَها وتوقيتَها بلا قرار، ثمّ عمودا «المسؤول المباشر والنائب المسؤول»،
    ثمّ الاعتمادُ النهائيّ من المدير أو من ينوب عنه — «لا يعتبر الطلب معتمداً الا
    باعتماد مدير المدرسة وتوقيعه عليه» (حاشية نموذج 02).
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
        max_length=12, choices=PERMIT_STAGES, default="secretary", verbose_name="المرحلة"
    )
    #: دورُ «المسؤول المباشر والنائب المسؤول» يومَ التقديم (م-21) — لقطةٌ لا تتبدّل
    #: بتبدّل دور الموظّف بعده. والفارغُ طلبُ مدير المدرسة نفسِه.
    deputy_role = models.CharField(max_length=30, blank=True, verbose_name="دور النائب المسؤول")
    #: قرارُ المدرسة (2026-09-19): المنسّقُ يوقّع استئذانَ المعلّم قبل النائب الأكاديميّ
    #: — وهو رئيسُ قسمه (``Department.head``) يومَ تسجيل السكرتارية رصيدَه، لقطةٌ لا تتبدّل.
    coordinator = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coordinated_permit_requests",
        verbose_name="منسّق المادّة",
    )
    coordinator_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coordinator_signed_permit_requests",
        verbose_name="وقّعه من المنسّقين",
    )
    coordinator_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت توقيع المنسّق")
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
        max_length=12, choices=PERMIT_STAGES, blank=True, verbose_name="مرحلة الرفض"
    )
    #: المادّة 79/3 من قانون الموارد البشرية: ما جاوز 3 ساعات للمرّة أو 10 في الشهر لا يُعتمد
    #: إلّا بموافقةٍ كتابيّة — فيُعلَّم الطلبُ عند التقديم، ويُثبَت مرجعُ الموافقة عند الاعتماد.
    over_limit = models.BooleanField(default=False, verbose_name="يجاوز الحدّ")
    written_approval_ref = models.CharField(
        max_length=300, blank=True, verbose_name="مرجع الموافقة الكتابية"
    )
    #: مرجعُ قرار رئيس المدير في إذن المدير نفسِه (بريدٌ أو كتابٌ وتاريخُه).
    external_reference = models.CharField(
        max_length=300, blank=True, verbose_name="مرجع اعتماد رئيس المدير"
    )
    #: م-19: «وإخطاره من قبل السكرتارية بالموافقة» — وقتُ الإخطار، وبه يجوز الخروج.
    notified_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت إخطار الموظف")
    #: م-25: قرارُ مربّع المدير (اعتماداً أو رفضاً) بيد نائب الشؤون الإدارية بالإنابة —
    #: يُوسم، واسمُ النائب في ``reviewed_by``.
    decided_on_behalf = models.BooleanField(default=False, verbose_name="قُرّر بالإنابة")

    @property
    def is_principals_own(self) -> bool:
        """طلبُ مدير المدرسة نفسِه — لا نائبَ مسؤولاً فوقه (``deputy_role`` فارغ)."""
        return not self.deputy_role

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "طلب إذن"
        verbose_name_plural = "طلبات الأذونات"
        constraints = [
            # م-14 (السياسة 3.5 و4.3): «لا يجوز الاذن أكثر من مرة واحدة في اليوم الواحد».
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
            # الإذنُ داخل يوم الدوام (7:00–14:00 = 420 دقيقة). وحدُّ المرّة (3 ساعات، م.79/3)
            # ليس قيداً في القاعدة: التجاوزُ جائزٌ بموافقةٍ كتابيّة (``over_limit``).
            # django-stubs 5.0.2 لا يعرف `condition` (Django 5.1).
            models.CheckConstraint(  # type: ignore[call-arg]
                condition=models.Q(duration_minutes__gt=0, duration_minutes__lte=420),
                name="permit_duration_within_workday",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "staff", "date"]),
            models.Index(fields=["school", "status", "stage"]),
        ]

    def __str__(self) -> str:
        return f"{self.staff.full_name} — {self.get_permit_type_display()} ({self.date})"


#: نموذج 03 «نموذج طلب» ([ن03] ص1، م-29 وم-31): «يجب ارفاق مع طلب استثناء الخروج المبكر
#: أو التأخير الصباحي ما يثبت حاجة الموظف لذلك».
EXCEPTION_TYPES = [
    ("late_arrival", "تأخير صباحي"),
    ("early_departure", "خروج مبكر"),
]

#: من يفتح مرفقَ نموذج 03 (قد يكون تقريراً طبيّاً): قيادةُ المدرسة — المديرُ ونائباه — لأنّ أيَّ
#: نائبٍ قد يُكلَّف بأعباء المدير فيقرّر النموذجَ (م-43)، ولا يقرّر من لا يرى ما يثبت الحاجة.
#: وصاحبُ الطلب يفتحه بملكيّته. (بوّابةُ الملفّات: ``governance/views_media.py``.)
EXCEPTION_EVIDENCE_ROLES = frozenset({"principal", "vice_admin", "vice_academic"})

EXCEPTION_STATUS = [
    ("pending", "قيد الانتظار"),
    ("approved", "معتمد"),
    ("rejected", "مرفوض"),
]


class AttendanceException(AuditedModel):
    """استثناءٌ من ساعة الحضور أو الانصراف لمدّةٍ من الأيّام — نموذج 03 بقرار المدير (م-30).

    **لماذا لا يُحمل على ``PermitRequest``:** الإذنُ يومٌ واحدٌ بثلاث ساعاتٍ أقصاه ومرّةٌ في
    اليوم وعشرُ ساعاتٍ في الشهر (م.79/3 و4.3)، ويمرّ بأربعة مربّعات. والاستثناءُ مدّةٌ من
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
    #: وصفٌ اختياريٌّ للمرفق — والمرفقُ نفسُه في ``evidence_file``.
    evidence = models.CharField(max_length=300, blank=True, verbose_name="وصف المرفق")
    #: م-31: «ما يثبت حاجة الموظف» — ملفٌّ إلزاميٌّ في الخدمة، ويُخدَم لصاحبه وللمدير
    #: ونائبه وحدَهم (``core/views_media.py``)، فقد يكون تقريراً طبيّاً.
    evidence_file = models.FileField(
        upload_to="attendance_exceptions/%Y/%m/",
        blank=True,
        null=True,
        verbose_name="المرفق (ما يثبت الحاجة)",
    )
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
    #: م-25 وم-30: قرارٌ بيد نائب الشؤون الإدارية بالإنابة عن المدير — يُوسم.
    decided_on_behalf = models.BooleanField(default=False, verbose_name="قُرّر بالإنابة")

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


#: الوظائفُ التي يُكلَّف موظّفٌ بأعبائها مؤقّتاً — وهي وظائفُ من يملك القرار في المدرسة.
ASSIGNABLE_ROLES = [
    ("principal", "مدير المدرسة"),
    ("vice_admin", "نائب المدير للشؤون الإدارية وشؤون الطلاب"),
    ("vice_academic", "نائب المدير للشؤون الأكاديمية"),
]


class StaffAssignment(AuditedModel):
    """تكليفٌ: ندبُ موظّفٍ مؤقّتاً للقيام بأعباء وظيفةٍ أخرى داخل المدرسة.

    سندُه نصّاً: المادّة 43 من النظام الوظيفيّ لموظفي المدارس (قرار مجلس الوزراء 32/2019):
    «يجوز لمدير المدرسة ندب الموظف للقيام مؤقتاً بأعباء وظيفة أخرى داخل المدرسة … لوظيفة
    مماثلة أو لوظيفة أعلى منها مباشرة، لمدة لا تجاوز عام أكاديمي» — وقانون الموارد البشرية،
    المادّة 53. وقرارُ المدرسة (2026-09-19): المديرُ يكلّف النائبَ الإداريّ أو الأكاديميّ
    (وغيرَهما من الإداريّين والأكاديميّين إن غابا معاً) بأعباء وظيفته، والنائبُ الأكاديميّ
    يكلّف أحدَ المنسّقين، والنائبُ الإداريّ أحدَ من تحت مسؤوليته.

    فالتكليفُ قرارٌ صريحٌ لا يقوم بغياب أحد: لا رصدُ غيابٍ يُنيب ولا أقدميّة. ولا يُحذف
    ولا يُعدَّل: رفعُه يكتب ``revoked_at``/``revoked_by``، فيبقى من كُلّف ومن كلّفه وبأيّ
    سبب — وقراراتُ المكلَّف تشير إلى معرّفه (``assignment``) في التدقيق.
    """

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="staff_assignments",
        verbose_name="المدرسة",
    )
    assignee = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="assignments_received",
        verbose_name="المكلَّف",
    )
    assigned_by = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="assignments_given",
        verbose_name="المكلِّف",
    )
    #: الوظيفةُ التي يقوم المكلَّفُ بأعبائها — وهي وظيفةُ المكلِّف نفسِه (المديرُ يكلّف عن
    #: المدير، والنائبُ عن النائب).
    acting_role = models.CharField(
        max_length=20, choices=ASSIGNABLE_ROLES, verbose_name="الوظيفة المكلَّف بأعبائها"
    )
    start_date = models.DateField(verbose_name="من تاريخ")
    end_date = models.DateField(verbose_name="إلى تاريخ")
    reason = models.CharField(max_length=300, verbose_name="سبب التكليف")
    #: مرجعُ قرار التكليف المكتوب (رقمٌ وتاريخ) إن وُجد.
    reference = models.CharField(max_length=200, blank=True, verbose_name="مرجع القرار")
    revoked_at = models.DateTimeField(null=True, blank=True, verbose_name="رُفع في")
    revoked_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assignments_revoked",
        verbose_name="رفعه",
    )

    class Meta:
        ordering = ["-start_date", "-created_at"]
        verbose_name = "تكليف"
        verbose_name_plural = "التكليفات"
        constraints = [
            # django-stubs 5.0.2 لا يعرف `condition` (Django 5.1).
            models.CheckConstraint(  # type: ignore[call-arg]
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="assignment_end_after_start",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "acting_role", "start_date", "end_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.assignee.full_name} — {self.get_acting_role_display()} ({self.start_date})"
