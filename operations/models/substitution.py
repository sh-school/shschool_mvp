"""غيابُ المعلّم وما يترتّب عليه: الإسنادُ البديل، وتبديلُ الحصص بين المعلّمين، والتعويضُ في حصّة زميل."""

from django.db import models

from core.models import ClassGroup, CustomUser, School

from .attendance import Session
from .common import _uuid
from .schedule import ScheduleSlot, Subject


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
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="teacher_absences", verbose_name="المدرسة"
    )
    teacher = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="absences_as_teacher",
        verbose_name="المعلّم",
    )
    date = models.DateField(verbose_name="تاريخ الغياب", db_index=True)
    reason = models.CharField(
        max_length=20, choices=REASON, default="other", verbose_name="سبب الغياب"
    )
    reason_notes = models.TextField(blank=True, verbose_name="تفاصيل")
    status = models.CharField(
        max_length=10, choices=STATUS, default="pending", db_index=True, verbose_name="الحالة"
    )
    reported_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reported_absences",
        verbose_name="سجّله",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

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
        TeacherAbsence,
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name="غياب المعلّم",
    )
    slot = models.ForeignKey(
        ScheduleSlot,
        on_delete=models.CASCADE,
        related_name="substitute_assignments",
        verbose_name="حصّة الجدول",
    )
    substitute = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="substitute_assignments",
        verbose_name="البديل",
    )
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="substitute_assignments",
        verbose_name="المدرسة",
    )
    status = models.CharField(
        max_length=10, choices=STATUS, default="assigned", verbose_name="الحالة"
    )
    assigned_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_assignments",
        verbose_name="كلّفه",
    )
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

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
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="teacher_swaps", verbose_name="المدرسة"
    )

    # المعلمان
    teacher_a = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="swaps_as_requester",
        verbose_name="المعلم الطالب",
    )
    teacher_b = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="swaps_as_target",
        verbose_name="المعلم المستهدف",
    )

    # الحصتان
    slot_a = models.ForeignKey(
        ScheduleSlot,
        on_delete=models.CASCADE,
        related_name="swaps_as_slot_a",
        verbose_name="حصة المعلم أ",
    )
    slot_b = models.ForeignKey(
        ScheduleSlot,
        on_delete=models.CASCADE,
        related_name="swaps_as_slot_b",
        verbose_name="حصة المعلم ب",
    )

    # تواريخ التبديل الفعلية
    swap_date_a = models.DateField(verbose_name="تاريخ حصة أ")
    swap_date_b = models.DateField(verbose_name="تاريخ حصة ب")

    swap_type = models.CharField(
        max_length=10, choices=SWAP_TYPE, default="same_day", verbose_name="نوع التبديل"
    )
    status = models.CharField(
        max_length=25, choices=STATUS, default="pending_b", db_index=True, verbose_name="الحالة"
    )

    # ربط اختياري بغياب (إذا التبديل بسبب غياب)
    absence = models.ForeignKey(
        TeacherAbsence,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="related_swaps",
        verbose_name="الغياب المرتبط",
    )

    # سلسلة الموافقة
    requested_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="swap_requests_created",
        verbose_name="مُنشئ الطلب",
    )
    b_responded_at = models.DateTimeField(
        null=True, blank=True, verbose_name="وقت ردّ المعلّم الثاني"
    )

    #: توقيعُ منسّقِ كلِّ مادّة على حِدَة.
    #:
    #: كان توقيعاً واحداً يملكه أيُّ منسّقٍ في المدرسة، ويذهب إلى النائب حين
    #: تختلف المادّتان. والتبديلُ يمسّ مادّتين وقسمَين، فلكلّ قسمٍ منسّقُه —
    #: وقرارُ القسم قرارُ صاحبه (قرار المستخدم 2026-09-11).
    #:
    #: والنائبُ الأكاديميُّ بديلٌ عن الغائب منهما لا متجاوزٌ عليهما: يوقّع عن
    #: جهةٍ لا منسّقَ لها، أو منسّقُها غائبٌ اليومَ، أو هو نفسُه طرفٌ في
    #: التبديل — وتُعلَّم البديلُ في `*_by_substitute` فيُقرأ في السجلّ.
    approved_a_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="swap_approvals_side_a",
        verbose_name="موافقةُ منسّق المادّة الأولى",
    )
    approved_a_at = models.DateTimeField(
        null=True, blank=True, verbose_name="وقت موافقة منسّق المادّة الأولى"
    )
    approved_a_by_substitute = models.BooleanField(
        default=False, verbose_name="وقّع عن منسّق المادّة الأولى بديلٌ"
    )
    approved_b_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="swap_approvals_side_b",
        verbose_name="موافقةُ منسّق المادّة الثانية",
    )
    approved_b_at = models.DateTimeField(
        null=True, blank=True, verbose_name="وقت موافقة منسّق المادّة الثانية"
    )
    approved_b_by_substitute = models.BooleanField(
        default=False, verbose_name="وقّع عن منسّق المادّة الثانية بديلٌ"
    )

    #: آخرُ من أتمّ الاعتماد — يبقى لتوافق الشاشات والسجلّات القديمة.
    approved_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="swap_approvals",
        verbose_name="المعتمِد",
    )
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ إتمام الاعتماد")
    executed_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت التنفيذ")

    reason = models.TextField(blank=True, verbose_name="سبب التبديل")
    rejection_reason = models.TextField(blank=True, verbose_name="سبب الرفض")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التعديل")

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
                condition=~models.Q(teacher_a=models.F("teacher_b")),
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
        """هل التبديل بين تخصصين مختلفين؟"""
        subj_a = self.slot_a.subject
        subj_b = self.slot_b.subject
        if subj_a and subj_b:
            return subj_a != subj_b
        return False

    @property
    def is_pending(self):
        return self.status in ("pending_b", "accepted_b", "pending_coordinator", "pending_vp")

    # ── المنسّقان: قرارُ القسم قرارُ صاحبه ───────────────────────────

    def coordinator_for(self, side: str):
        """منسّقُ قسمِ معلّم هذه الجهة — أو `None` إن كان المقعدُ شاغراً.

        ولا رابطَ بين المادّة والقسم في القاعدة؛ الرابطُ عضويّةُ المعلّم.
        فمنسّقُ المادّة هو رئيسُ قسمِ من يُدرّسها في هذه الحصّة.
        """
        teacher = self.teacher_a if side == "a" else self.teacher_b
        department = teacher.department_obj if teacher else None
        return department.head if department else None

    def needs_one_signature(self) -> bool:
        """جهةٌ واحدةٌ حين يجمعهما منسّقٌ واحد — فلا يُطلب توقيعُه مرّتين."""
        first, second = self.coordinator_for("a"), self.coordinator_for("b")
        return first is not None and first == second

    @property
    def is_fully_approved(self) -> bool:
        if self.needs_one_signature():
            return bool(self.approved_a_by_id or self.approved_b_by_id)
        return bool(self.approved_a_by_id and self.approved_b_by_id)

    @property
    def awaiting_sides(self) -> tuple[str, ...]:
        """الجهاتُ التي لم تُوقَّع بعد — تقرؤها الشاشةُ لتقول لمن تنتظر."""
        if self.is_fully_approved:
            return ()
        if self.needs_one_signature():
            return ("a",)
        return tuple(side for side in ("a", "b") if not getattr(self, f"approved_{side}_by_id"))

    def sides_display(self):
        """ما تعرضه البطاقةُ عن الجهتين: من وقّع ومن يُنتظَر.

        ويُحسب في النموذج لا في القالب: القالبُ لا يستدعي دالّةً بمعاملات،
        ونسخُ المنطق فيه يجعل الشاشةَ تقول غيرَ ما تفعله الخدمة.
        """
        shown = []
        for side in ("a", "b"):
            if side == "b" and self.needs_one_signature():
                continue
            slot = self.slot_a if side == "a" else self.slot_b
            signer = getattr(self, f"approved_{side}_by")
            head = self.coordinator_for(side)
            shown.append(
                (
                    side,
                    {
                        "subject": str(slot.subject) if slot.subject else "المادّة",
                        "signed": signer is not None,
                        "who": (
                            signer.full_name
                            if signer
                            else (head.full_name if head else "النائب الأكاديميّ")
                        ),
                        "substitute": getattr(self, f"approved_{side}_by_substitute"),
                    },
                )
            )
        return shown

    # ── المدى: ينتهي بانتهاء الحصّة الأبعد ──────────────────────────

    @property
    def last_period_end(self):
        """لحظةُ انتهاء آخرِ الحصّتين — بها ينقضي التبديل.

        قرارُ المستخدم 2026-09-11: «يعود الجدول كما كان عند انتهاء الحصّة
        البعيدة المبدَّلة». ولا يحتاج ذلك إجراءً ولا مهمّةً مجدولة: التبديلُ
        لا يمسّ قالبَ الأسبوع أصلاً، فهو يعود من نفسه.
        """
        from datetime import datetime

        pairs = (
            (self.swap_date_a, self.slot_a.end_time),
            (self.swap_date_b, self.slot_b.end_time),
        )
        return max(datetime.combine(day, end) for day, end in pairs)

    @property
    def has_ended(self) -> bool:
        from django.utils import timezone as tz

        return tz.localtime(tz.now()).replace(tzinfo=None) > self.last_period_end


class CompensatorySession(models.Model):
    """
    حصة تعويضية — المعلم يعوّض حصة فاتته بسبب غياب.
    القيد: أسبوع واحد كحد أقصى (week_offset: 0 أو 1)

    وموضعُها حصّةُ زميلٍ يدرّس الشعبةَ نفسها، بموافقته (قرارُ المالك 2026-09-24):
    الجدولُ المعتمد ممتلئ، فلا حصّةَ فارغةً لشعبةٍ يُعوَّض فيها. يوافق الزميلُ
    أوّلاً ثمّ يعتمد المنسّق، فتصير حصّتُه ذلك اليومَ لصاحب التعويض بمادّته.
    """

    STATUS = [
        ("colleague", "بانتظار موافقة الزميل"),
        ("pending", "بانتظار الاعتماد"),
        ("approved", "معتمدة"),
        ("completed", "مكتملة"),
        ("cancelled", "ملغاة"),
        ("expired", "انتهت المهلة"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="compensatory_sessions",
        verbose_name="المدرسة",
    )

    teacher = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="compensatory_sessions",
        verbose_name="المعلم",
    )
    original_slot = models.ForeignKey(
        ScheduleSlot,
        on_delete=models.CASCADE,
        related_name="compensatory_originals",
        verbose_name="الحصة الأصلية (الفائتة)",
    )
    absence = models.ForeignKey(
        TeacherAbsence,
        on_delete=models.CASCADE,
        related_name="compensatory_sessions",
        verbose_name="الغياب المرتبط",
    )

    # تفاصيل الحصة التعويضية
    compensatory_date = models.DateField(verbose_name="تاريخ التعويض")
    compensatory_period = models.IntegerField(verbose_name="رقم حصة التعويض")
    class_group = models.ForeignKey(
        ClassGroup,
        on_delete=models.CASCADE,
        related_name="compensatory_sessions",
        verbose_name="الشعبة",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="compensatory_sessions",
        verbose_name="المادة",
    )

    #: صاحبُ الحصّة التي يُعوَّض فيها — وفارغٌ إن كانت الشعبةُ فارغةً في وقتها.
    colleague = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="compensatory_hosted",
        verbose_name="الزميل صاحب الحصّة",
    )
    colleague_responded_at = models.DateTimeField(
        null=True, blank=True, verbose_name="وقت ردّ الزميل"
    )

    # 0 = نفس الأسبوع, 1 = الأسبوع التالي
    week_offset = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="أسبوع التعويض",
        help_text="0 = نفس الأسبوع, 1 = الأسبوع التالي (الحد الأقصى)",
    )

    status = models.CharField(
        max_length=10, choices=STATUS, default="pending", db_index=True, verbose_name="الحالة"
    )

    # الموافقة
    approved_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="compensatory_approvals",
        verbose_name="المعتمِد",
    )
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الاعتماد")

    # الربط بالحصة الفعلية بعد الإنشاء
    session_created = models.ForeignKey(
        Session,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="compensatory_source",
        verbose_name="الحصة المنشأة",
    )

    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التعديل")

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
                condition=models.Q(week_offset__lte=1),
                name="compensatory_max_one_week",
            ),
        ]

    @property
    def is_open(self) -> bool:
        """طلبٌ ما زال ينتظر قراراً: زميلٍ أو منسّق."""
        return self.status in ("colleague", "pending")

    def __str__(self):
        return (
            f"تعويض: {self.teacher.full_name} | {self.subject or 'مادة'} "
            f"| {self.compensatory_date} ح{self.compensatory_period} "
            f"| {self.get_status_display()}"
        )
