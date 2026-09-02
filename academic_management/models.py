"""
خطّةُ نصاب المعلّم ومؤهّلاتُه — الحقيقةُ الإداريّةُ التي لا يحملها الجدول.

    ObservedScheduledWorkload ≠ ApprovedWorkload

فمعلّمٌ ظهر في الجدول بأربعَ عشرةَ حصّةً قد يكون نصابُه الرسميُّ ثمانيَ عشرةَ
وله تخفيضُ منسّقِ مادّة. والجدولُ لا يحمل هذه الحقيقة: ليس فيه حقلٌ للنصاب
المطلوب ولا للتخفيض ولا لمن اعتمده. فهذه الوحدةُ تحملها.

    TeachingTarget = RequiredWeeklyPeriods − ApprovedReductionPeriods
    ∑ AssignedInstructionalPeriods = TeachingTarget   (بعد الاعتماد فقط)
    CanTeach ≠ AssignedToTeach ≠ ActuallyScheduled
    InstructionalPeriods ≠ OccupiedSlots

وثلاثةُ أشياءَ كشفها قياسُ الجدول القائم هي التي شكّلت هذا التصميم: ستّةَ
عشرَ معلّماً يعملون في مرحلتين — فالتفصيلُ حسب المرحلة موجود؛ وثلاثةَ عشرَ
يدرّسون أكثرَ من مادّة — فالمؤهّلُ سجلٌّ مستقلٌّ لكلّ مادّة؛ وخمسةٌ لهم حصصٌ
في شعبةٍ منقسمة — فالنصابُ يُعدّ بالحصص لا بالخانات.

ولا شيءَ هنا يُشتقّ من الجدول: `HistoricalAssignment → Proposal` لا `→ Truth`.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models.base import AuditedModel

# ── دورةُ الخطّة ─────────────────────────────────────────────────────
# «قيد المراجعة» و«روجعت» حالتان لا واحدة: الأولى تقول إنّ المُدخِل رفع يدَه
# عن المسودّة، والثانية تقول إنّ مراجعاً بعينه نظر فيها وختمها. ولو جُمعتا في
# حالةٍ واحدةٍ لما عرفنا أيَّهما جرى.
DRAFT = "draft"
SUBMITTED = "submitted"
REVIEWED = "reviewed"
APPROVED = "approved"
LOCKED = "locked"

PLAN_STATUSES = [
    (DRAFT, "مسودّة"),
    (SUBMITTED, "قيد المراجعة"),
    (REVIEWED, "روجعت — بانتظار الاعتماد"),
    (APPROVED, "معتمدة"),
    (LOCKED, "مقفلة للجدولة"),
]

#: التسلسلُ المسموح — ولا قفزَ فوق مرحلة.
FORWARD = {
    DRAFT: (SUBMITTED,),
    SUBMITTED: (REVIEWED, DRAFT),  # الردُّ إلى المُدخِل رجوعٌ مشروع
    REVIEWED: (APPROVED, DRAFT),
    APPROVED: (LOCKED,),
    LOCKED: (),
}

#: بعد الاعتماد لا يُكتب فوق النسخة — يُولَّد إصدارٌ جديد.
FROZEN_STATUSES = (APPROVED, LOCKED)

#: الحالاتُ التي يجوز فيها تحريرُ محتوى الخطّة.
EDITABLE_STATUSES = (DRAFT,)

# ── حالاتُ المؤهّل ──────────────────────────────────────────────────
PRIMARY = "primary"
QUALIFIED = "qualified"
ALLOWED = "allowed"
NOT_APPROVED = "not_approved"

QUALIFICATION_STATUSES = [
    (PRIMARY, "تخصّصٌ أساسيّ"),
    (QUALIFIED, "مؤهَّل"),
    (ALLOWED, "مسموحٌ به"),
    (NOT_APPROVED, "غيرُ معتمَد"),
]

#: ما يُجيز التدريسَ فعلاً — و«غيرُ معتمَد» ليس منها، وغيابُ السجلّ كذلك.
PERMITTING = (PRIMARY, QUALIFIED, ALLOWED)

LEVEL_TYPES = [("prep", "إعدادي"), ("sec", "ثانوي")]

#: مصدرُ الحقيقة الإداريّة — ولا «مشتقٌّ من الجدول» بينها.
SOURCES = [
    ("ministry", "قرارُ الوزارة"),
    ("school", "قرارُ إدارة المدرسة"),
    ("department", "قرارُ القسم الأكاديميّ"),
    ("other", "أخرى"),
]

# ── من أين جاء الرقم؟ ───────────────────────────────────────────────
#: ثلاثةُ منابعَ لا رابعَ لها، وأخبثُها الرابعُ الممنوع: «ثمانيةَ عشرَ لأنّ
#: الجميعَ يعرف أنّ النصابَ ثمانيةَ عشر». فالمعرفةُ الشائعةُ ليست مصدراً.
FROM_POLICY = "policy"
FROM_PREVIOUS_PLAN = "previous_plan"
FROM_MANUAL = "manual"

PROVENANCE_KINDS = [
    (FROM_POLICY, "سياسةُ نصابٍ مسجّلة"),
    (FROM_PREVIOUS_PLAN, "نسخٌ من خطّةٍ سابقة"),
    (FROM_MANUAL, "إدخالٌ إداريٌّ موثَّق"),
]


class ApprovedPlanImmutableError(Exception):
    """محاولةُ الكتابة فوق نسخةٍ معتمَدة.

    ولا يُكتفى بالمنع في `clean()`: الاعتمادُ حقيقةٌ إداريّةٌ وُقِّعت، فيُحرَس
    عند `save()` كي لا يمرّ تعديلٌ من سكربتٍ أو من `admin` بلا تحقّق.
    """


class TeacherWorkloadPlan(AuditedModel):
    """رأسُ خطّة النصاب لمعلّمٍ في عامٍ ونسخةٍ بعينها."""

    school = models.ForeignKey(
        "core.School", on_delete=models.CASCADE, related_name="workload_plans"
    )
    teacher = models.ForeignKey(
        "core.CustomUser", on_delete=models.CASCADE, related_name="workload_plans"
    )
    academic_year = models.CharField(max_length=9, verbose_name="العام الدراسي")
    plan_version = models.PositiveIntegerField(default=1, verbose_name="نسخة الخطة")

    # ── النصابُ ومن أين جاء ──────────────────────────────────────
    required_weekly_periods = models.PositiveIntegerField(verbose_name="النصاب الأسبوعي المعتمد")
    required_source_kind = models.CharField(
        max_length=14,
        choices=PROVENANCE_KINDS,
        default=FROM_MANUAL,
        verbose_name="منبع النصاب",
    )
    required_source_reference = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="مرجع النصاب",
        help_text="رقمُ التعميم أو المحضر أو رمزُ السياسة",
    )
    #: منبعُ `previous_plan` — النسخةُ التي نُسخ عنها الرقم، صريحةً لا ضمناً.
    required_source_plan = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="copied_into",
        verbose_name="منسوخٌ عن خطّة",
    )
    #: يومَ تُسجَّل `WorkloadPolicy` يصير هذا `ForeignKey` إليها. واليومَ رمزٌ
    #: نصّيٌّ لسياسةٍ نعرفها ولا نملك جدولَها بعد — ولا نخترع الجدولَ لنملأه.
    required_policy_key = models.CharField(
        max_length=60, blank=True, verbose_name="رمز سياسة النصاب"
    )

    # ── التخفيضُ ومن أين جاء ─────────────────────────────────────
    reduction_periods = models.PositiveIntegerField(default=0, verbose_name="حصص التخفيض")
    reduction_reason = models.CharField(max_length=200, blank=True, verbose_name="سبب التخفيض")
    reduction_source = models.CharField(
        max_length=12, choices=SOURCES, blank=True, verbose_name="جهة قرار التخفيض"
    )
    reduction_source_reference = models.CharField(
        max_length=200, blank=True, verbose_name="مرجع قرار التخفيض"
    )

    # ── الدورةُ ومن فعل ماذا ومتى ────────────────────────────────
    status = models.CharField(max_length=10, choices=PLAN_STATUSES, default=DRAFT)
    submitted_by = models.ForeignKey(
        "core.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_workload_plans",
        verbose_name="رفعها للمراجعة",
    )
    submitted_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الرفع")
    reviewed_by = models.ForeignKey(
        "core.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_workload_plans",
        verbose_name="راجعها",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ المراجعة")
    review_comment = models.CharField(max_length=400, blank=True, verbose_name="ملاحظة المراجع")
    approved_by = models.ForeignKey(
        "core.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_workload_plans",
        verbose_name="اعتمدها",
    )
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الاعتماد")
    #: جمعُ المراجعةِ والاعتمادِ في شخصٍ واحد — لا يقع صامتاً.
    self_approval_override = models.BooleanField(default=False, verbose_name="اعتُمدت بمن راجعها")

    # ── بصمةُ ما فُحص لحظةَ الاعتماد ─────────────────────────────
    # المعاملةُ تمنع التغيّرَ **أثناء** الاعتماد، ولا تقول بعد ستّةِ أشهرٍ ما
    # الذي كان قائماً حينه. وبلا هذه البصمة تبدو خطّةٌ اختلف عنها الإسنادُ
    # لاحقاً وكأنّها كانت خاطئةً منذ البداية — والفرقُ بين «صحّت ثمّ تباعدت»
    # و«وُلدت خاطئة» هو الفرقُ بين تعويضٍ وإدانة.
    validated_at = models.DateTimeField(null=True, blank=True, verbose_name="لحظة الفحص")
    validated_assignment_count = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="عدد الإسنادات المفحوصة"
    )
    validated_assignment_periods = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="حصص الإسنادات المفحوصة"
    )
    validation_fingerprint = models.CharField(
        max_length=64, blank=True, verbose_name="بصمة الإسنادات المفحوصة"
    )

    class Meta:
        verbose_name = "خطة نصاب معلم"
        verbose_name_plural = "خطط أنصبة المعلمين"
        ordering = ["teacher__full_name", "-plan_version"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "teacher", "academic_year", "plan_version"],
                name="unique_workload_plan_version",
            ),
            models.CheckConstraint(
                condition=models.Q(reduction_periods__lte=models.F("required_weekly_periods")),
                name="reduction_within_required_load",
            ),
        ]

    def __str__(self):
        return f"{self.teacher} — {self.academic_year} v{self.plan_version}"

    # ── الثابتُ الأوّل ────────────────────────────────────────────

    @property
    def teaching_target(self):
        """`RequiredWeeklyPeriods − ApprovedReductionPeriods` — محسوبٌ لا مخزَّن.

        ولو خُزِّن لأمكن أن يقول الحقلُ شيئاً ويقول الطرحُ غيرَه، فيصير في
        القاعدة مصدران لحقيقةٍ واحدة. وهو بعينه الخللُ الذي كلّفنا سبعةَ عشرَ
        سجلّاً في `SubjectClassAssignment.weekly_periods`.
        """
        return self.required_weekly_periods - self.reduction_periods

    @property
    def allocations_balanced(self):
        """التفصيلُ حسب المرحلة اختياريّ — فإن وُجد لزم أن يبلغ الهدف."""
        rows = list(self.allocations.all())
        if not rows:
            return True
        return sum(a.target_periods for a in rows) == self.teaching_target

    def validate_allocations(self):
        if not self.allocations_balanced:
            total = sum(a.target_periods for a in self.allocations.all())
            raise ValidationError(
                f"مجموعُ التفصيل حسب المرحلة {total} "
                f"ولا يساوي الهدفَ التدريسيّ {self.teaching_target}."
            )

    def discrepancy(self, observed):
        """الفرقُ بين المرصود والمعتمد — يُوصف ولا يُسمّى خطأً.

        فقد يكون تكليفاً إداريّاً طارئاً أو نيابةً أو تغييراً لم يُصدَر له
        إصدارٌ جديدٌ بعد. والحكمُ لمن يعرف التكليف.
        """
        return {
            "observed": observed,
            "approved": self.teaching_target,
            "delta": observed - self.teaching_target,
            "is_error": False,
            "note": "فرقٌ يحتاج تفسيراً — لا يُحكم عليه بالخطأ من الجدول وحده.",
        }

    # ── الحراسة ──────────────────────────────────────────────────

    @classmethod
    def current_for(cls, school, teacher, academic_year):
        """أحدثُ نسخةٍ **معتمَدة** — والمسوّدةُ لا تصير سياسةً لأنّها الأحدث."""
        return (
            cls.objects.filter(
                school=school,
                teacher=teacher,
                academic_year=academic_year,
                status__in=FROZEN_STATUSES,
            )
            .order_by("-plan_version")
            .first()
        )

    # ── مصادرُ الحقائق ───────────────────────────────────────────

    def provenance_gaps(self):
        """كلُّ حقيقةٍ إداريّةٍ مؤثّرةٍ لها منبعُها — لا منبعٌ واحدٌ للخطّة كلّها.

        فقد يكون النصابُ ثمانيةَ عشرَ بتعميمٍ وزاريّ، والتخفيضُ حصّتين بقرارِ
        مديرٍ، والتخصّصُ رياضياتٍ بملفِّ موظّف — ثلاثةُ مصادرَ لا يجمعها حقلٌ
        واحد. فيُسأل كلُّ رقمٍ عن منبعه على حدة.

        تُعيد قائمةَ ما ينقص، وفارغةً تعني أنّ كلَّ رقمٍ يعرف من أين جاء.
        """
        gaps = []
        kind = self.required_source_kind
        if kind == FROM_PREVIOUS_PLAN:
            if not self.required_source_plan_id:
                gaps.append("النصابُ منسوخٌ عن خطّةٍ سابقة ولم تُذكر الخطّة.")
        elif kind == FROM_POLICY:
            if not (self.required_policy_key.strip() or self.required_source_reference.strip()):
                gaps.append("النصابُ من سياسةٍ ولم يُذكر رمزُها ولا مرجعُها.")
        else:  # manual
            if not self.required_source_reference.strip():
                gaps.append("النصابُ إدخالٌ يدويّ بلا مرجعٍ موثَّق.")

        if self.reduction_periods:
            if not self.reduction_reason.strip():
                gaps.append("التخفيضُ بلا سبب.")
            if not self.reduction_source:
                gaps.append("التخفيضُ بلا جهةٍ أصدرته.")
            if not self.reduction_source_reference.strip():
                gaps.append("التخفيضُ بلا مرجعِ قرار.")
        return gaps

    @property
    def has_provenance(self):
        return not self.provenance_gaps()

    def clean(self):
        super().clean()
        if self.reduction_periods > self.required_weekly_periods:
            raise ValidationError({"reduction_periods": "التخفيضُ لا يتجاوز النصابَ المعتمد."})
        if self.reduction_periods and not self.reduction_reason.strip():
            raise ValidationError(
                {"reduction_reason": "التخفيضُ قرارٌ إداريّ — ورقمٌ بلا سببٍ لا يُراجَع."}
            )
        if (
            self.required_source_kind == FROM_PREVIOUS_PLAN
            and self.required_source_plan_id == self.pk
        ):
            raise ValidationError({"required_source_plan": "خطّةٌ لا تُنسخ عن نفسها."})

    #: ما يجوز تغييرُه بعد الاعتماد: الانتقالُ إلى القفل وحدَه.
    _MUTABLE_AFTER_APPROVAL = frozenset(
        {
            "status",
            "approved_at",
            "approved_by_id",
            "self_approval_override",
            "validated_at",
            "validated_assignment_count",
            "validated_assignment_periods",
            "validation_fingerprint",
            "updated_at",
            "updated_by_id",
        }
    )

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).first()
            if previous and previous.status in FROZEN_STATUSES:
                changed = self._changed_fields(previous)
                if changed:
                    raise ApprovedPlanImmutableError(
                        "نسخةٌ معتمَدةٌ لا تُعدَّل في مكانها — أنشئ إصداراً جديداً. "
                        f"الحقولُ التي حاولتَ تغييرها: {'، '.join(sorted(changed))}"
                    )
        if self.status in FROZEN_STATUSES and self.approved_at is None:
            self.approved_at = timezone.now()
        super().save(*args, **kwargs)

    def _changed_fields(self, previous):
        names = {
            f.attname
            for f in self._meta.concrete_fields
            if f.attname not in self._MUTABLE_AFTER_APPROVAL
        }
        changed = {n for n in names if getattr(self, n) != getattr(previous, n)}
        # الانتقالُ الوحيدُ المسموح بعد الاعتماد: APPROVED ← LOCKED.
        if self.status != previous.status and self.status != LOCKED:
            changed.add("status")
        return changed


class TeacherWorkloadAllocation(models.Model):
    """تفصيلُ الهدف التدريسيّ حسب المرحلة — اختياريٌّ عند الحاجة.

    ستّةَ عشرَ معلّماً في المدرسة يعملون في الإعداديّ والثانويّ معاً، فحشرُ
    نصابهم في رقمٍ واحدٍ يُخفي أين يقع. ومن يعمل في مرحلةٍ واحدةٍ لا يحتاج
    هذا التفصيل، فلا يُفرض عليه.

    ولا تخفيضَ هنا: التخفيضُ الرسميُّ كلُّه يعيش في رأس الخطّة
    `TeacherWorkloadPlan.reduction_periods` بسببه ومصدره. ولو حمل التوزيعُ
    رقمَ تخفيضٍ ثانياً لصار عندنا تخفيضٌ على الرأس وتخفيضاتٌ على المراحل
    ولا نعرف أيُّهما الحقيقة. فالتوزيعُ يوزّع الهدفَ التدريسيَّ وحدَه:

        ∑ Allocation.target_periods = Plan.teaching_target

    وإن جاء يوماً قرارٌ يقول صراحةً «تخفيضُ حصّتين من نصاب الثانويّ» فالجوابُ
    كيانٌ مستقلٌّ له السببُ والنطاقُ والمصدر، لا رقمٌ ثانٍ يُحشر هنا.
    """

    workload_plan = models.ForeignKey(
        TeacherWorkloadPlan, on_delete=models.CASCADE, related_name="allocations"
    )
    level_type = models.CharField(max_length=4, choices=LEVEL_TYPES, verbose_name="المرحلة")
    target_periods = models.PositiveIntegerField(verbose_name="الحصص المستهدفة")
    notes = models.CharField(max_length=200, blank=True, verbose_name="ملاحظات")

    class Meta:
        verbose_name = "توزيع نصاب حسب المرحلة"
        verbose_name_plural = "توزيعات النصاب حسب المرحلة"
        ordering = ["level_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["workload_plan", "level_type"], name="unique_allocation_per_level"
            )
        ]

    def __str__(self):
        return f"{self.get_level_type_display()} — {self.target_periods}"

    def clean(self):
        """التجاوزُ خطأٌ في كلّ حال، والنقصُ خطأٌ عند الاعتماد وحدَه.

        فالتوزيعُ يُبنى على دفعات: من يكتب `prep = 10` أوّلاً لم يُخطئ لأنّ
        الهدفَ ستّةَ عشرَ، وإنّما يُنتظر منه `sec = 6`. أمّا من كتب ما يتجاوز
        الهدفَ فقد أخطأ الآن. وتمامُ المجموع يُحرَس في بوّابة الاعتماد عبر
        `TeacherWorkloadPlan.validate_allocations()`.
        """
        super().clean()
        target = self.workload_plan.teaching_target
        others = (
            self.workload_plan.allocations.exclude(pk=self.pk)
            if self.pk
            else self.workload_plan.allocations.all()
        )
        total = sum(a.target_periods for a in others) + (self.target_periods or 0)
        if total > target:
            raise ValidationError(
                {"target_periods": f"مجموعُ التوزيع {total} يتجاوز الهدفَ التدريسيّ {target}."}
            )


class WorkloadGovernance(models.Model):
    """من يُدخل ومن يراجع ومن يعتمد — تهيئةٌ للمدرسة لا اسمُ وظيفةٍ في الكود.

    بحثنا فلم نجد نصّاً وزاريّاً منشوراً يقول إنّ اعتمادَ الأنصبة اختصاصُ
    المديرِ حصراً أو النائبِ الأكاديميِّ حصراً. فتثبيتُ اسمِ وظيفةٍ في الكود
    ادّعاءُ حقيقةٍ تنظيميّةٍ لا نملك دليلَها. والصوابُ قدرةٌ تُربط بدور:

        WORKLOAD_EDIT → WORKLOAD_REVIEW → WORKLOAD_APPROVE

    والافتراضُ الموصى به «منسّق ← نائبٌ أكاديميّ ← مدير» يبقى افتراضاً
    قابلاً للتهيئة، لا قاعدةً قطريّةً محفورة. وفراغُ القائمة يعني «خُذ
    الافتراضَ»، لا «لا أحدَ يملك القدرة».
    """

    school = models.OneToOneField(
        "core.School", on_delete=models.CASCADE, related_name="workload_governance"
    )
    edit_roles = models.JSONField(default=list, blank=True, verbose_name="أدوار الإدخال")
    review_roles = models.JSONField(default=list, blank=True, verbose_name="أدوار المراجعة")
    approve_roles = models.JSONField(default=list, blank=True, verbose_name="أدوار الاعتماد")

    #: الفصلُ بين المراجع والمعتمِد هو الأصل — لا لنصٍّ وزاريٍّ يوجبه، بل
    #: لأنّ `reviewed_by == approved_by` يُلغي المراجعةَ المستقلّةَ عمليّاً.
    #: والمدرسةُ الصغيرةُ قد تحتاج الجمعَ يوماً، فيكون تجاوزاً مسجّلاً في
    #: سجلّ التدقيق لا سلوكاً صامتاً.
    allow_self_approval = models.BooleanField(
        default=False, verbose_name="يجوز أن يعتمدها من راجعها"
    )

    class Meta:
        verbose_name = "حوكمة أنصبة المدرسة"
        verbose_name_plural = "حوكمة أنصبة المدارس"

    def __str__(self):
        return f"حوكمة الأنصبة — {self.school}"

    @classmethod
    def for_school(cls, school):
        """تهيئةُ المدرسة إن وُجدت، وإلّا كائنٌ غيرُ محفوظٍ بالافتراضات."""
        return cls.objects.filter(school=school).first() or cls(school=school)


class TeacherSubjectQualification(AuditedModel):
    """ما **يستطيع** المعلّم تدريسَه — لا ما ظهر فيه هذا العام.

        CanTeach ≠ AssignedToTeach ≠ ActuallyScheduled

    وظهورُ معلّمٍ في مادّةٍ في جدولٍ واحدٍ لا يُثبت أنّه لا يستطيع غيرَها،
    ولا يُنشئ له مؤهّلاً. والمؤهّلُ قرارٌ يُسنَد إلى مصدرٍ ويُؤرَّخ.
    """

    school = models.ForeignKey(
        "core.School", on_delete=models.CASCADE, related_name="teacher_qualifications"
    )
    teacher = models.ForeignKey(
        "core.CustomUser", on_delete=models.CASCADE, related_name="subject_qualifications"
    )
    subject = models.ForeignKey(
        "operations.Subject", on_delete=models.CASCADE, related_name="teacher_qualifications"
    )
    #: فارغٌ يعني «كلَّ المراحل» — فقد يُعتمد لمادّةٍ في الإعداديّ دون الثانويّ.
    level_type = models.CharField(
        max_length=4, choices=LEVEL_TYPES, blank=True, verbose_name="المرحلة"
    )

    qualification_status = models.CharField(
        max_length=12, choices=QUALIFICATION_STATUSES, default=QUALIFIED
    )
    is_primary = models.BooleanField(default=False, verbose_name="تخصّصه الأساسي؟")
    source = models.CharField(max_length=12, choices=SOURCES, default="school")
    source_reference = models.CharField(max_length=200, blank=True, verbose_name="مرجع القرار")
    valid_from = models.DateField(verbose_name="سارٍ من")
    valid_to = models.DateField(null=True, blank=True, verbose_name="سارٍ حتى")

    class Meta:
        verbose_name = "مؤهل معلم لمادة"
        verbose_name_plural = "مؤهلات المعلمين للمواد"
        ordering = ["teacher__full_name", "subject__name_ar"]
        constraints = [
            models.UniqueConstraint(
                fields=["teacher", "subject", "level_type"],
                name="unique_qualification_per_level",
            )
        ]

    def __str__(self):
        scope = self.get_level_type_display() if self.level_type else "كل المراحل"
        return f"{self.teacher} — {self.subject} ({scope})"

    def is_valid_on(self, on=None):
        on = on or timezone.localdate()
        if self.valid_from and on < self.valid_from:
            return False
        return not (self.valid_to and on > self.valid_to)

    @property
    def permits_teaching(self):
        return self.qualification_status in PERMITTING

    def provenance_gaps(self):
        """المؤهّلُ حقيقةٌ إداريّةٌ ثالثة — ولها منبعُها هي الأخرى.

        فمن قال إنّ هذا المعلّمَ يدرّس الرياضيات؟ ملفُّ الموظّف؟ قرارُ قسم؟
        الجوابُ يُكتب، ولا يُترك لأنّ «الجميعَ يعرف».
        """
        gaps = []
        if not self.source_reference.strip():
            gaps.append(f"مؤهّلُ {self.subject} بلا مرجعٍ موثَّق.")
        if not self.valid_from:
            gaps.append(f"مؤهّلُ {self.subject} بلا تاريخِ سريان.")
        return gaps

    def clean(self):
        super().clean()
        if not self.source_reference.strip():
            raise ValidationError(
                {"source_reference": "المؤهّلُ قرارٌ يُسنَد إلى مصدرٍ — ومرجعُه لا يُترك فارغاً."}
            )
        if self.is_primary and self.qualification_status != PRIMARY:
            raise ValidationError({"is_primary": "«تخصّصٌ أساسيّ» علمٌ وحالة — فلا يختلفان."})
        if self.valid_to and self.valid_from and self.valid_to < self.valid_from:
            raise ValidationError({"valid_to": "نهايةُ السريان قبل بدايته."})
        if self.is_primary:
            clash = TeacherSubjectQualification.objects.filter(
                teacher=self.teacher, level_type=self.level_type, is_primary=True
            ).exclude(pk=self.pk)
            if clash.exists():
                raise ValidationError({"is_primary": "للمعلّم تخصّصٌ أساسيٌّ واحدٌ في المرحلة الواحدة."})


def can_teach(teacher, subject, level_type="", on=None):
    """هل يجوز إسنادُ هذه المادّة لهذا المعلّم؟

    وغيابُ السجلّ **ليس إذناً**: لا يُستنتج المؤهّلُ من الصمت ولا من ظهور
    المعلّم في الجدول. والمؤهّلُ العامّ (بلا مرحلة) يغطّي المراحلَ كلَّها،
    والمقيَّدُ بمرحلةٍ لا يتعدّاها.
    """
    scopes = {"", level_type} if level_type else {""}
    rows = TeacherSubjectQualification.objects.filter(
        teacher=teacher, subject=subject, level_type__in=scopes
    )
    return any(r.permits_teaching and r.is_valid_on(on) for r in rows)
