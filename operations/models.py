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
        CustomUser, on_delete=models.CASCADE, related_name="sessions", verbose_name="المعلم"
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
    teacher = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="schedule_slots")
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
        unique_together = ("school", "period_number", "day_type")
        ordering = ["day_type", "period_number"]

    def __str__(self):
        if self.is_break:
            return f"استراحة ({self.break_label}) {self.start_time:%H:%M}-{self.end_time:%H:%M}"
        return f"ح{self.period_number} ({self.get_day_type_display()}) {self.start_time:%H:%M}-{self.end_time:%H:%M}"


class SubjectClassAssignment(models.Model):
    """ربط مادة بفصل بمعلم — المصفوفة الأساسية للتوليد التلقائي"""

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="subject_assignments")
    class_group = models.ForeignKey(ClassGroup, on_delete=models.CASCADE, related_name="subject_assignments")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="class_assignments")
    teacher = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="subject_assignments")
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
        return f"{self.subject.name_ar} → {self.class_group} ({self.teacher.full_name}) [{self.weekly_periods}ح/أسبوع]"


class TeacherPreference(models.Model):
    """تفضيلات المعلم للجدولة الذكية"""

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    teacher = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="schedule_preferences")
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="teacher_preferences")
    academic_year = models.CharField(max_length=9, default=settings.CURRENT_ACADEMIC_YEAR)
    max_daily_periods = models.PositiveIntegerField(default=5, verbose_name="أقصى حصص يومية")
    max_consecutive = models.PositiveIntegerField(default=3, verbose_name="أقصى حصص متتالية")
    free_day = models.IntegerField(
        null=True, blank=True, choices=ScheduleSlot.DAYS,
        verbose_name="يوم التفريغ المفضل",
    )
    notes = models.TextField(blank=True, verbose_name="ملاحظات")

    class Meta:
        verbose_name = "تفضيلات معلم"
        verbose_name_plural = "تفضيلات المعلمين"
        unique_together = ("teacher", "school", "academic_year")

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
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="schedule_generations")
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
        return f"توليد {self.academic_year} — {self.get_status_display()} ({self.quality_score:.0f}%)"
