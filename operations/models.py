import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import ClassGroup, CustomUser, School


def _uuid():
    return uuid.uuid4()


class Subject(models.Model):
    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="subjects")
    name_ar = models.CharField(max_length=100, verbose_name="اسم المادة")
    code = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = "مادة دراسية"
        verbose_name_plural = "المواد الدراسية"
        ordering = ["name_ar"]
        indexes = [
            models.Index(fields=["school", "name_ar"], name="idx_subject_school_name"),
        ]

    def __str__(self):
        return self.name_ar


class Session(models.Model):
    STATUS = [
        ("scheduled", "مجدولة"),
        ("in_progress", "جارية"),
        ("completed", "مكتملة"),
        ("cancelled", "ملغاة"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="sessions")
    class_group = models.ForeignKey(ClassGroup, on_delete=models.CASCADE, related_name="sessions")
    teacher = models.ForeignKey(
        CustomUser, on_delete=models.PROTECT, related_name="sessions", verbose_name="المعلم"
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name="sessions"
    )
    date = models.DateField(verbose_name="التاريخ", db_index=True)
    start_time = models.TimeField(verbose_name="وقت البدء")
    end_time = models.TimeField(verbose_name="وقت النهاية")
    status = models.CharField(max_length=15, choices=STATUS, default="scheduled", db_index=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "حصة"
        verbose_name_plural = "الحصص"
        indexes = [
            models.Index(fields=["school", "date"]),
            models.Index(fields=["teacher", "date"]),
            models.Index(fields=["class_group", "date"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["teacher", "date", "start_time"], name="no_teacher_time_overlap"
            ),
            models.UniqueConstraint(
                fields=["class_group", "date", "start_time"], name="no_class_time_overlap"
            ),
        ]

    def __str__(self):
        return f"{self.subject or 'حصة'} | {self.class_group} | {self.date} {self.start_time}"

    @property
    def is_today(self):
        return self.date == timezone.now().date()

    @property
    def attendance_count(self):
        return self.attendances.count()

    @property
    def present_count(self):
        return self.attendances.filter(status="present").count()

    @present_count.setter
    def present_count(self, value):
        pass  # يسمح لـ Django ORM بضبط القيمة المُحسَّبة (annotate)


class StudentAttendance(models.Model):
    STATUS = [
        ("present", "حاضر"),
        ("absent", "غائب"),
        ("late", "متأخر"),
        ("excused", "معذور"),
    ]
    EXCUSE = [
        ("medical", "طبي"),
        ("family", "ظروف عائلية"),
        ("official", "رسمي"),
        ("other", "أخرى"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="attendances")
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="attendances")
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="attendances")
    status = models.CharField(max_length=10, choices=STATUS, default="present", db_index=True)
    excuse_type = models.CharField(max_length=20, choices=EXCUSE, blank=True)
    excuse_notes = models.TextField(blank=True)
    marked_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, related_name="marked_attendances"
    )
    marked_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "حضور طالب"
        verbose_name_plural = "سجلات الحضور"
        constraints = [
            models.UniqueConstraint(
                fields=["session", "student"], name="unique_attendance_per_session"
            )
        ]
        indexes = [
            models.Index(fields=["school", "session"]),
            models.Index(fields=["student", "status"]),
            models.Index(fields=["student", "status", "marked_at"]),
        ]

    def __str__(self):
        return f"{self.student.full_name} | {self.get_status_display()} | {self.session}"


# ─────────────────────────────────────────────
# المرحلة 2 — الجداول الذكية + نظام البديل
# ─────────────────────────────────────────────


class ScheduleSlot(models.Model):
    """حصة ثابتة في الجدول الأسبوعي (مستقلة عن Session اليومية)"""

    DAYS = [
        (0, "الأحد"),
        (1, "الاثنين"),
        (2, "الثلاثاء"),
        (3, "الأربعاء"),
        (4, "الخميس"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="schedule_slots")
    teacher = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name="schedule_slots")
    class_group = models.ForeignKey(
        ClassGroup, on_delete=models.CASCADE, related_name="schedule_slots"
    )
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True)
    day_of_week = models.IntegerField(choices=DAYS, verbose_name="اليوم")
    period_number = models.IntegerField(verbose_name="رقم الحصة")  # 1..7
    start_time = models.TimeField(verbose_name="وقت البدء")
    end_time = models.TimeField(verbose_name="وقت النهاية")
    academic_year = models.CharField(max_length=9, default=settings.CURRENT_ACADEMIC_YEAR)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default="", verbose_name="ملاحظات")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "حصة جدول"
        verbose_name_plural = "جدول الحصص"
        constraints = [
            models.UniqueConstraint(
                fields=["teacher", "day_of_week", "period_number", "academic_year"],
                condition=models.Q(is_active=True),
                name="no_teacher_period_overlap",
            ),
            models.UniqueConstraint(
                fields=["class_group", "day_of_week", "period_number", "academic_year"],
                condition=models.Q(is_active=True),
                name="no_class_period_overlap",
            ),
        ]
        ordering = ["day_of_week", "period_number"]

    def __str__(self):
        return f"{self.get_day_of_week_display()} | ح{self.period_number} | {self.teacher.full_name} | {self.class_group}"

    @property
    def day_name(self):
        return dict(self.DAYS).get(self.day_of_week, "")


class TeacherAbsence(models.Model):
    """تسجيل غياب معلم (يُفعِّل نظام البديل)"""

    REASON = [
        ("sick", "إجازة مرضية"),
        ("official", "مهمة رسمية"),
        ("emergency", "ظرف طارئ"),
        ("training", "تدريب"),
        ("other", "أخرى"),
    ]
    STATUS = [
        ("pending", "بانتظار البديل"),
        ("covered", "مغطّى"),
        ("uncovered", "غير مغطّى"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="teacher_absences")
    teacher = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="absences_as_teacher"
    )
    date = models.DateField(verbose_name="تاريخ الغياب", db_index=True)
    reason = models.CharField(max_length=20, choices=REASON, default="other")
    reason_notes = models.TextField(blank=True, verbose_name="تفاصيل")
    status = models.CharField(max_length=10, choices=STATUS, default="pending", db_index=True)
    reported_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reported_absences",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "غياب معلم"
        verbose_name_plural = "غيابات المعلمين"
        constraints = [
            models.UniqueConstraint(fields=["teacher", "date"], name="one_absence_per_teacher_day")
        ]
        ordering = ["-date"]

    def __str__(self):
        return f"{self.teacher.full_name} — {self.date} ({self.get_reason_display()})"


class SubstituteAssignment(models.Model):
    """تعيين بديل لحصة معلم غائب"""

    STATUS = [
        ("assigned", "مُعيَّن"),
        ("confirmed", "قبِل"),
        ("declined", "رفض"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    absence = models.ForeignKey(
        TeacherAbsence, on_delete=models.CASCADE, related_name="assignments"
    )
    slot = models.ForeignKey(
        ScheduleSlot, on_delete=models.CASCADE, related_name="substitute_assignments"
    )
    substitute = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="substitute_assignments"
    )
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="substitute_assignments"
    )
    status = models.CharField(max_length=10, choices=STATUS, default="assigned")
    assigned_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, related_name="created_assignments"
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "تعيين بديل"
        verbose_name_plural = "تعيينات البدلاء"
        constraints = [
            models.UniqueConstraint(
                fields=["slot", "absence"], name="one_substitute_per_slot_absence"
            )
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"بديل: {self.substitute.full_name} → {self.slot}"


class AbsenceAlert(models.Model):
    STATUS = [
        ("pending", "قيد المراجعة"),
        ("notified", "تم الإبلاغ"),
        ("resolved", "تم الحل"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="absence_alerts")
    absence_count = models.IntegerField()
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS, default="pending", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    resolved_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name="resolved_alerts"
    )

    class Meta:
        verbose_name = "تنبيه غياب"
        verbose_name_plural = "تنبيهات الغياب"
        ordering = ["-created_at"]

    def __str__(self):
        return f"تنبيه: {self.student.full_name} | {self.absence_count} يوم"


# ─────────────────────────────────────────────
# المرحلة 3 — الجدولة الذكية
# ─────────────────────────────────────────────


class TimeSlotConfig(models.Model):
    """إعدادات الحصص الزمنية للمدرسة — تُعرِّف توقيت كل حصة"""

    DAY_TYPES = [
        ("regular", "عادي (أحد-أربعاء)"),
        ("thursday", "خميس"),
        ("ramadan", "رمضان"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="time_slots_config")
    period_number = models.PositiveIntegerField(verbose_name="رقم الحصة")
    start_time = models.TimeField(verbose_name="وقت البدء")
    end_time = models.TimeField(verbose_name="وقت الانتهاء")
    day_type = models.CharField(max_length=10, choices=DAY_TYPES, default="regular")
    is_break = models.BooleanField(default=False, verbose_name="استراحة؟")
    break_label = models.CharField(max_length=50, blank=True, verbose_name="نوع الاستراحة")

    class Meta:
        verbose_name = "إعداد حصة زمنية"
        verbose_name_plural = "إعدادات الحصص الزمنية"
        ordering = ["day_type", "period_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "period_number", "day_type"],
                name="unique_timeslot_config",
            ),
        ]

    def __str__(self):
        if self.is_break:
            return f"استراحة ({self.break_label}) {self.start_time:%H:%M}-{self.end_time:%H:%M}"
        return f"ح{self.period_number} ({self.get_day_type_display()}) {self.start_time:%H:%M}-{self.end_time:%H:%M}"


class SubjectClassAssignment(models.Model):
    """ربط مادة بفصل بمعلم — المصفوفة الأساسية للتوليد التلقائي"""

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="subject_assignments")
    class_group = models.ForeignKey(
        ClassGroup, on_delete=models.CASCADE, related_name="subject_assignments"
    )
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="class_assignments")
    teacher = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="subject_assignments",
        null=True,
        blank=True,
        verbose_name="المعلم",
    )
    weekly_periods = models.PositiveIntegerField(verbose_name="عدد الحصص الأسبوعية")
    academic_year = models.CharField(max_length=9, default=settings.CURRENT_ACADEMIC_YEAR)
    requires_lab = models.BooleanField(default=False, verbose_name="يحتاج معمل؟")
    preferred_periods = models.JSONField(default=list, blank=True, verbose_name="حصص مفضلة")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "توزيع مادة على فصل"
        verbose_name_plural = "توزيع المواد على الفصول"
        constraints = [
            models.UniqueConstraint(
                fields=["class_group", "subject", "academic_year"],
                name="unique_subject_per_class_year",
            )
        ]
        ordering = ["class_group__grade", "class_group__section", "subject__name_ar"]

    def __str__(self):
        teacher_name = self.teacher.full_name if self.teacher else "غير محدد"
        return f"{self.subject.name_ar} → {self.class_group} ({teacher_name}) [{self.weekly_periods}ح/أسبوع]"


class TeacherPreference(models.Model):
    """تفضيلات المعلم للجدولة الذكية"""

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    teacher = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="schedule_preferences"
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="teacher_preferences")
    academic_year = models.CharField(max_length=9, default=settings.CURRENT_ACADEMIC_YEAR)
    max_daily_periods = models.PositiveIntegerField(default=5, verbose_name="أقصى حصص يومية")
    max_consecutive = models.PositiveIntegerField(default=3, verbose_name="أقصى حصص متتالية")
    free_day = models.IntegerField(
        null=True,
        blank=True,
        choices=ScheduleSlot.DAYS,
        verbose_name="يوم التفريغ المفضل",
    )
    notes = models.TextField(blank=True, verbose_name="ملاحظات")

    class Meta:
        verbose_name = "تفضيلات معلم"
        verbose_name_plural = "تفضيلات المعلمين"
        constraints = [
            models.UniqueConstraint(
                fields=["teacher", "school", "academic_year"],
                name="unique_teacher_schedule_pref",
            ),
        ]

    def __str__(self):
        return f"تفضيلات: {self.teacher.full_name} ({self.academic_year})"


class ScheduleGeneration(models.Model):
    """سجل عمليات التوليد التلقائي للجدول"""

    STATUS = [
        ("draft", "مسودة"),
        ("approved", "معتمد"),
        ("archived", "مؤرشف"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="schedule_generations"
    )
    academic_year = models.CharField(max_length=9)
    generated_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=STATUS, default="draft")
    quality_score = models.FloatField(default=0, verbose_name="نقاط الجودة (0-100)")
    hard_violations = models.IntegerField(default=0, verbose_name="انتهاكات صلبة")
    soft_violations = models.JSONField(default=dict, verbose_name="انتهاكات مرنة")
    total_slots_created = models.IntegerField(default=0)
    generation_time_ms = models.IntegerField(default=0, verbose_name="زمن التوليد (مللي ثانية)")
    config_snapshot = models.JSONField(default=dict, verbose_name="نسخة الإعدادات")

    class Meta:
        verbose_name = "عملية توليد جدول"
        verbose_name_plural = "عمليات توليد الجدول"
        ordering = ["-generated_at"]

    def __str__(self):
        return (
            f"توليد {self.academic_year} — {self.get_status_display()} ({self.quality_score:.0f}%)"
        )


# ═════════════════════════════════════════════════════════════════════
# المرحلة 2 — التبديل والتعويض وسجل الحصص الحرة
# المرجع: خطة الجدول الذكي الشامل (7 مراحل)
# ═════════════════════════════════════════════════════════════════════


class TeacherSwap(models.Model):
    """
    تبديل بين معلمين — يمر بمسار موافقة:
    المعلم أ → المعلم ب (قبول/رفض) → المنسق (موافقة) → تنفيذ
    القيد: التبديل مع معلمي نفس الصف فقط (إلا بصلاحية أعلى)
    """

    SWAP_TYPE = [
        ("same_day", "تبديل نفس اليوم"),
        ("cross_day", "تبديل بين يومين"),
    ]
    STATUS = [
        ("pending_b", "بانتظار موافقة المعلم"),
        ("accepted_b", "المعلم وافق — بانتظار المنسق"),
        ("rejected_b", "المعلم رفض"),
        ("pending_coordinator", "بانتظار المنسق"),
        ("pending_vp", "بانتظار النائب (تخصصات مختلفة)"),
        ("approved", "معتمد"),
        ("executed", "تم التنفيذ"),
        ("rejected", "مرفوض"),
        ("cancelled", "ملغى"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="teacher_swaps")

    # المعلمان
    teacher_a = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="swaps_as_requester",
        verbose_name="المعلم الطالب",
    )
    teacher_b = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="swaps_as_target",
        verbose_name="المعلم المستهدف",
    )

    # الحصتان
    slot_a = models.ForeignKey(
        ScheduleSlot, on_delete=models.CASCADE, related_name="swaps_as_slot_a",
        verbose_name="حصة المعلم أ",
    )
    slot_b = models.ForeignKey(
        ScheduleSlot, on_delete=models.CASCADE, related_name="swaps_as_slot_b",
        verbose_name="حصة المعلم ب",
    )

    # تواريخ التبديل الفعلية
    swap_date_a = models.DateField(verbose_name="تاريخ حصة أ")
    swap_date_b = models.DateField(verbose_name="تاريخ حصة ب")

    swap_type = models.CharField(max_length=10, choices=SWAP_TYPE, default="same_day")
    status = models.CharField(max_length=25, choices=STATUS, default="pending_b", db_index=True)

    # ربط اختياري بغياب (إذا التبديل بسبب غياب)
    absence = models.ForeignKey(
        TeacherAbsence, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="related_swaps", verbose_name="الغياب المرتبط",
    )

    # سلسلة الموافقة
    requested_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True,
        related_name="swap_requests_created", verbose_name="مُنشئ الطلب",
    )
    b_responded_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="swap_approvals", verbose_name="المعتمِد",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)

    reason = models.TextField(blank=True, verbose_name="سبب التبديل")
    rejection_reason = models.TextField(blank=True, verbose_name="سبب الرفض")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "طلب تبديل"
        verbose_name_plural = "طلبات التبديل"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "status"]),
            models.Index(fields=["teacher_a", "status"]),
            models.Index(fields=["teacher_b", "status"]),
            models.Index(fields=["swap_date_a"]),
        ]
        constraints = [
            # لا يمكن أن يكون نفس المعلم طرفي التبديل
            models.CheckConstraint(
                check=~models.Q(teacher_a=models.F("teacher_b")),
                name="swap_different_teachers",
            ),
        ]

    def __str__(self):
        return (
            f"تبديل: {self.teacher_a.full_name} <-> {self.teacher_b.full_name} "
            f"| {self.get_status_display()}"
        )

    @property
    def is_cross_department(self):
        """هل التبديل بين تخصصين مختلفين؟ (يحتاج نائب بدل منسق)"""
        subj_a = self.slot_a.subject
        subj_b = self.slot_b.subject
        if subj_a and subj_b:
            return subj_a != subj_b
        return False

    @property
    def is_pending(self):
        return self.status in ("pending_b", "accepted_b", "pending_coordinator", "pending_vp")


class CompensatorySession(models.Model):
    """
    حصة تعويضية — المعلم يعوّض حصة فاتته بسبب غياب.
    القيد: أسبوع واحد كحد أقصى (week_offset: 0 أو 1)
    """

    STATUS = [
        ("pending", "بانتظار الموافقة"),
        ("approved", "معتمدة"),
        ("completed", "مكتملة"),
        ("cancelled", "ملغاة"),
        ("expired", "انتهت المهلة"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="compensatory_sessions")

    teacher = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="compensatory_sessions",
        verbose_name="المعلم",
    )
    original_slot = models.ForeignKey(
        ScheduleSlot, on_delete=models.CASCADE, related_name="compensatory_originals",
        verbose_name="الحصة الأصلية (الفائتة)",
    )
    absence = models.ForeignKey(
        TeacherAbsence, on_delete=models.CASCADE, related_name="compensatory_sessions",
        verbose_name="الغياب المرتبط",
    )

    # تفاصيل الحصة التعويضية
    compensatory_date = models.DateField(verbose_name="تاريخ التعويض")
    compensatory_period = models.IntegerField(verbose_name="رقم حصة التعويض")
    class_group = models.ForeignKey(
        ClassGroup, on_delete=models.CASCADE, related_name="compensatory_sessions",
        verbose_name="الشعبة",
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="compensatory_sessions", verbose_name="المادة",
    )

    # 0 = نفس الأسبوع, 1 = الأسبوع التالي
    week_offset = models.PositiveSmallIntegerField(
        default=0, verbose_name="أسبوع التعويض",
        help_text="0 = نفس الأسبوع, 1 = الأسبوع التالي (الحد الأقصى)",
    )

    status = models.CharField(max_length=10, choices=STATUS, default="pending", db_index=True)

    # الموافقة
    approved_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="compensatory_approvals", verbose_name="المعتمِد",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    # الربط بالحصة الفعلية بعد الإنشاء
    session_created = models.ForeignKey(
        Session, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="compensatory_source", verbose_name="الحصة المنشأة",
    )

    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "حصة تعويضية"
        verbose_name_plural = "الحصص التعويضية"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "status"]),
            models.Index(fields=["teacher", "status"]),
            models.Index(fields=["compensatory_date"]),
        ]
        constraints = [
            # لا يمكن تعويض حصتين بنفس الوقت لنفس المعلم
            models.UniqueConstraint(
                fields=["teacher", "compensatory_date", "compensatory_period"],
                condition=~models.Q(status__in=["cancelled", "expired"]),
                name="unique_compensatory_slot",
            ),
            # week_offset بين 0 و 1 فقط
            models.CheckConstraint(
                check=models.Q(week_offset__lte=1),
                name="compensatory_max_one_week",
            ),
        ]

    def __str__(self):
        return (
            f"تعويض: {self.teacher.full_name} | {self.subject or 'مادة'} "
            f"| {self.compensatory_date} ح{self.compensatory_period} "
            f"| {self.get_status_display()}"
        )


class FreeSlotRegistry(models.Model):
    """
    سجل الحصص الحرة لكل معلم — يُبنى تلقائياً من فراغات ScheduleSlot.
    يُستخدم لتسهيل البحث عن بديل أو وقت تعويض.
    """

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    teacher = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="free_slots",
        verbose_name="المعلم",
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="free_slots")
    day_of_week = models.IntegerField(choices=ScheduleSlot.DAYS, verbose_name="اليوم")
    period_number = models.IntegerField(verbose_name="رقم الحصة")
    academic_year = models.CharField(max_length=9, default=settings.CURRENT_ACADEMIC_YEAR)
    is_available = models.BooleanField(
        default=True, verbose_name="متاح؟",
        help_text="False = محجوز مؤقتاً (تعويض أو مهمة)",
    )
    reserved_for = models.ForeignKey(
        "CompensatorySession", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="reserved_slots",
        verbose_name="محجوز لحصة تعويضية",
    )

    class Meta:
        verbose_name = "حصة حرة"
        verbose_name_plural = "سجل الحصص الحرة"
        ordering = ["day_of_week", "period_number"]
        indexes = [
            models.Index(fields=["school", "day_of_week", "period_number"]),
            models.Index(fields=["teacher", "is_available"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["teacher", "day_of_week", "period_number", "academic_year"],
                name="unique_free_slot_entry",
            ),
        ]

    def __str__(self):
        day = dict(ScheduleSlot.DAYS).get(self.day_of_week, "")
        avail = "متاح" if self.is_available else "محجوز"
        return f"{self.teacher.full_name} | {day} ح{self.period_number} | {avail}"


# ═════════════════════════════════════════════════════════════════════
# تقييم أداء الموظفين — قرار مجلس الوزراء 32/2019 المادة 15
# التقييم السنوي للأداء الوظيفي وفق المعايير الخمسة المعتمدة
# ═════════════════════════════════════════════════════════════════════


class StaffEvaluation(models.Model):
    """
    تقييم الأداء السنوي للموظف — قرار مجلس الوزراء 32/2019 م.15

    المعايير الخمسة (كل منها 1-5):
        1. المعرفة المهنية
        2. فاعلية التدريس
        3. تقييم الطلاب
        4. التطوير المهني
        5. المجتمع المدرسي

    الدرجة الكلية = متوسط المعايير الخمسة (محسوبة تلقائياً)
    """

    RECOMMENDATION_CHOICES = [
        ("excellent", "ممتاز"),
        ("very_good", "جيد جداً"),
        ("good", "جيد"),
        ("acceptable", "مقبول"),
        ("needs_improvement", "يحتاج تحسين"),
        ("unsatisfactory", "غير مُرضٍ"),
    ]
    STATUS_CHOICES = [
        ("draft", "مسودة"),
        ("submitted", "مُقدَّم"),
        ("approved", "معتمد"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)

    # ── الأطراف ────────────────────────────────────────────────────
    staff = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="evaluations_as_staff",
        verbose_name="الموظف",
    )
    evaluator = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="evaluations_as_evaluator",
        verbose_name="المقيّم",
    )
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="staff_evaluations",
        verbose_name="المدرسة",
    )

    # ── الفترة ─────────────────────────────────────────────────────
    academic_year = models.CharField(
        max_length=9,
        default=settings.CURRENT_ACADEMIC_YEAR,
        verbose_name="العام الأكاديمي",
        db_index=True,
    )
    evaluation_date = models.DateField(verbose_name="تاريخ التقييم")

    # ── المعايير الخمسة (1-5) ──────────────────────────────────────
    professional_knowledge = models.PositiveSmallIntegerField(
        verbose_name="المعرفة المهنية",
        help_text="1 = ضعيف، 5 = ممتاز",
    )
    teaching_effectiveness = models.PositiveSmallIntegerField(
        verbose_name="فاعلية التدريس",
        help_text="1 = ضعيف، 5 = ممتاز",
    )
    student_assessment = models.PositiveSmallIntegerField(
        verbose_name="تقييم الطلاب",
        help_text="1 = ضعيف، 5 = ممتاز",
    )
    professional_development = models.PositiveSmallIntegerField(
        verbose_name="التطوير المهني",
        help_text="1 = ضعيف، 5 = ممتاز",
    )
    school_community = models.PositiveSmallIntegerField(
        verbose_name="المجتمع المدرسي",
        help_text="1 = ضعيف، 5 = ممتاز",
    )

    # ── النتيجة ────────────────────────────────────────────────────
    overall_score = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        verbose_name="الدرجة الكلية",
        help_text="متوسط المعايير الخمسة — يُحسب تلقائياً عند الحفظ",
        editable=False,
    )
    recommendation = models.CharField(
        max_length=20,
        choices=RECOMMENDATION_CHOICES,
        verbose_name="التوصية",
    )
    notes = models.TextField(blank=True, verbose_name="ملاحظات")

    # ── الحالة ─────────────────────────────────────────────────────
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="draft",
        verbose_name="الحالة",
        db_index=True,
    )

    # ── الطوابع الزمنية ───────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التعديل")

    class Meta:
        verbose_name = "تقييم أداء موظف"
        verbose_name_plural = "تقييمات أداء الموظفين"
        ordering = ["-evaluation_date"]
        indexes = [
            models.Index(fields=["school", "academic_year"]),
            models.Index(fields=["staff", "academic_year"]),
            models.Index(fields=["evaluator", "academic_year"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["staff", "academic_year", "school"],
                name="unique_staff_evaluation_per_year",
            ),
            # كل معيار بين 1 و 5
            models.CheckConstraint(
                check=models.Q(professional_knowledge__gte=1, professional_knowledge__lte=5),
                name="eval_knowledge_range_1_5",
            ),
            models.CheckConstraint(
                check=models.Q(teaching_effectiveness__gte=1, teaching_effectiveness__lte=5),
                name="eval_teaching_range_1_5",
            ),
            models.CheckConstraint(
                check=models.Q(student_assessment__gte=1, student_assessment__lte=5),
                name="eval_assessment_range_1_5",
            ),
            models.CheckConstraint(
                check=models.Q(professional_development__gte=1, professional_development__lte=5),
                name="eval_development_range_1_5",
            ),
            models.CheckConstraint(
                check=models.Q(school_community__gte=1, school_community__lte=5),
                name="eval_community_range_1_5",
            ),
        ]

    def __str__(self):
        return (
            f"تقييم: {self.staff.full_name} | {self.academic_year} "
            f"| {self.get_recommendation_display()} ({self.overall_score})"
        )

    def save(self, *args, **kwargs):
        """حساب الدرجة الكلية تلقائياً قبل الحفظ."""
        from decimal import Decimal

        criteria = [
            self.professional_knowledge,
            self.teaching_effectiveness,
            self.student_assessment,
            self.professional_development,
            self.school_community,
        ]
        self.overall_score = Decimal(str(round(sum(criteria) / len(criteria), 2)))
        super().save(*args, **kwargs)

    @property
    def criteria_dict(self):
        """يُعيد المعايير كقاموس — مفيد للعرض والتقارير."""
        return {
            "المعرفة المهنية": self.professional_knowledge,
            "فاعلية التدريس": self.teaching_effectiveness,
            "تقييم الطلاب": self.student_assessment,
            "التطوير المهني": self.professional_development,
            "المجتمع المدرسي": self.school_community,
        }
