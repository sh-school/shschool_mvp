"""الجدول الدراسيّ: الموادّ، والحصصُ الأسبوعيّة، وإسنادُ المادّة للشعبة، وتفضيلاتُ المعلّمين وتفريغاتُهم، وخطُّ الأساس وقيودُه، وسجلُّ التوليد، والحصصُ الشاغرة."""

from django.db import models

from core.academic_calendar import default_academic_year
from core.models import ClassGroup, CustomUser, School
from core.models.base import AuditedModel
from core.querysets import YearScopedQuerySet

from .common import _uuid


class Subject(models.Model):
    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="subjects", verbose_name="المدرسة"
    )
    name_ar = models.CharField(max_length=100, verbose_name="اسم المادة")
    code = models.CharField(max_length=20, blank=True, verbose_name="رمز المادّة")
    #: طبيعةُ المادّة تربويّاً — تقرؤها مؤشراتُ الجودة (التوقيت التربويّ): الثقيلةُ
    #: يُفضَّل لها النصفُ الأوّل من اليوم، والنشاطُ النصفُ الثاني، والعاديّةُ بلا
    #: تفضيل. حقلٌ لا قائمةُ أسماءٍ في الكود — فسياسةُ المدرسة تتغيّر بلا نشر.
    PEDAGOGY = [
        ("heavy", "ثقيلة (رياضيات، علوم، لغات)"),
        ("activity", "نشاط (بدنية، فنون، تكنولوجيا)"),
        ("regular", "عادية"),
    ]
    pedagogy = models.CharField(
        max_length=10, choices=PEDAGOGY, default="regular", verbose_name="طبيعة المادة"
    )
    requires_double_period = models.BooleanField(
        default=False,
        verbose_name="حصة مزدوجة",
        help_text="يتطلب حصتين متتاليتين بدون استراحة",
    )

    class Meta:
        verbose_name = "مادة دراسية"
        verbose_name_plural = "المواد الدراسية"
        ordering = ["name_ar"]
        indexes = [
            models.Index(fields=["school", "name_ar"], name="idx_subject_school_name"),
        ]

    def __str__(self):
        return self.name_ar


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
    #: حصصُ اليوم — مصدرٌ واحدٌ يقرؤه المولّدُ واستمارةُ التفريغ وقوائمُ الحصص.
    #: وكان الرقمُ سبعةً مكتوباً في ثلاثة مواضع، فمدرسةٌ بثمانٍ تكسر أحدَها صامتاً.
    PERIODS_PER_DAY = 7
    PERIODS = list(range(1, PERIODS_PER_DAY + 1))

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="schedule_slots", verbose_name="المدرسة"
    )
    teacher = models.ForeignKey(
        CustomUser, on_delete=models.PROTECT, related_name="schedule_slots", verbose_name="المعلّم"
    )
    class_group = models.ForeignKey(
        ClassGroup, on_delete=models.CASCADE, related_name="schedule_slots", verbose_name="الشعبة"
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="المادّة"
    )
    day_of_week = models.IntegerField(choices=DAYS, verbose_name="اليوم")
    period_number = models.IntegerField(verbose_name="رقم الحصة")  # 1..7
    start_time = models.TimeField(verbose_name="وقت البدء")
    end_time = models.TimeField(verbose_name="وقت النهاية")
    academic_year = models.CharField(
        max_length=9, default=default_academic_year, verbose_name="العام الدراسي"
    )
    #: مجموعة الاختيار حين تنقسم الشعبة في الحصّة الواحدة.
    #:
    #: أربعُ شعبٍ يتفرّق طلابها بين مادّتين في التوقيت نفسه: 11/1 و12/1 بين
    #: التكنولوجيا والفنون البصرية، و11/4 و12/4 بين الكيمياء والفنون. قسمٌ
    #: يذهب إلى معمل الحاسب أو غرفة الفنون، وقسمٌ يبقى.
    #:
    #: وهي فارغةٌ في حصص الشعبة كاملةً — وهي الغالبة — فيبقى القيد عليها
    #: كما كان: حصّةٌ واحدة لشعبةٍ في التوقيت الواحد.
    elective_group = models.CharField(
        max_length=40, blank=True, default="", verbose_name="مجموعة الاختيار"
    )
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    #: أيُّ توليدٍ أنتج هذه الحصّة — فارغٌ للحصص اليدويّة ولِما سبق هذا الحقل.
    #: وبه يصير الاعتمادُ فعلاً: تُفعَّل حصصُ التوليد المعتمَد وتُطفأ سواها،
    #: وكانت الحصصُ تُفعَّل لحظةَ التوليد فيراها المعلّمون قبل أن يُقرَّر شيء.
    generation = models.ForeignKey(
        "ScheduleGeneration",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="slots",
        verbose_name="التوليد المصدر",
    )
    notes = models.TextField(blank=True, default="", verbose_name="ملاحظات")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    objects = YearScopedQuerySet.as_manager()

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
                fields=[
                    "class_group",
                    "day_of_week",
                    "period_number",
                    "academic_year",
                    "elective_group",
                ],
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
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="time_slots_config", verbose_name="المدرسة"
    )
    period_number = models.PositiveIntegerField(verbose_name="رقم الحصة")
    start_time = models.TimeField(verbose_name="وقت البدء")
    end_time = models.TimeField(verbose_name="وقت الانتهاء")
    day_type = models.CharField(
        max_length=10, choices=DAY_TYPES, default="regular", verbose_name="نوع اليوم"
    )
    #: جرسُ النطاق — فارغٌ يعني جرسَ المدرسة الافتراضيّ الذي يرثه من لا نطاقَ له.
    band = models.ForeignKey(
        "core.TimeBand",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="time_slots",
        verbose_name="نطاق التوقيت",
    )
    is_break = models.BooleanField(default=False, verbose_name="استراحة؟")
    break_label = models.CharField(max_length=50, blank=True, verbose_name="نوع الاستراحة")

    class Meta:
        verbose_name = "إعداد حصة زمنية"
        verbose_name_plural = "إعدادات الحصص الزمنية"
        ordering = ["band__order", "day_type", "period_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "band", "period_number", "day_type"],
                name="unique_timeslot_config",
            ),
        ]

    def __str__(self):
        if self.is_break:
            return f"استراحة ({self.break_label}) {self.start_time:%H:%M}-{self.end_time:%H:%M}"
        return f"ح{self.period_number} ({self.get_day_type_display()}) {self.start_time:%H:%M}-{self.end_time:%H:%M}"


class SubjectClassAssignment(AuditedModel):
    """ربط مادة بفصل بمعلم — المصفوفة الأساسية للتوليد التلقائي.

    وهو **قرارٌ إداريّ** لا سجلُّ بيانات: من أسند هذه المادّة لهذا المعلّم،
    ومتى، ولماذا خالف الخطّة إن خالفها. وكان قبل هذا يُكتب ويُمحى بلا أثر —
    فمن غيّر معلّمَ شعبةٍ في نوفمبر لم يترك ما يدلّ عليه.

        ObservedAssignment ≠ ApprovedAssignment

    ولذلك يرث `AuditedModel`: أنشأه ومتى، وعدّله ومتى. و`updated_at` منه هو
    الطابعُ الذي يحرس التزامنَ في `assignment_services` — فآخرُ من يضغط «حفظ»
    ليس أحقَّ بالحقيقة من زميلٍ سبقه.
    """

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="subject_assignments", verbose_name="المدرسة"
    )
    class_group = models.ForeignKey(
        ClassGroup,
        on_delete=models.CASCADE,
        related_name="subject_assignments",
        verbose_name="الشعبة",
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="class_assignments", verbose_name="المادّة"
    )
    teacher = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="subject_assignments",
        null=True,
        blank=True,
        verbose_name="المعلم",
    )
    weekly_periods = models.PositiveIntegerField(verbose_name="عدد الحصص الأسبوعية")
    academic_year = models.CharField(
        max_length=9, default=default_academic_year, verbose_name="العام الدراسي"
    )
    requires_lab = models.BooleanField(default=False, verbose_name="يحتاج معمل؟")
    #: وسمُ المجموعة المتوازية: مادّتان في الشعبة الواحدة تحملان الوسمَ نفسه
    #: تُدرَّسان في التوقيت نفسه لقسمَي الطلاب — كالفنون والتكنولوجيا في 11/1.
    #:
    #: وكان هذا مسجّلاً في `ScheduleSlot.elective_group` وحدَه، أي في الجدول
    #: المستورَد لا في الإسناد. فكان تحذيرُ الطاقة يعدّ الحصصَ ويقيسها
    #: بالخانات فيُنذر كاذباً، والمولّدُ لا يعرف الازدواجَ فيعدّ إحدى
    #: المادّتين متعذّرة:
    #:
    #:     InstructionalPeriods ≠ OccupiedSlots
    parallel_group = models.CharField(
        max_length=40, blank=True, default="", verbose_name="مجموعة التوازي"
    )
    #: قرارُ الازدواج لهذه الشعبة وحدَها — و`None` يعني «اتبع المادّة».
    #:
    #: فالازدواجُ ليس صفةَ المادّة بإطلاق بل صفةَ تدريسها في صفٍّ بعينه:
    #: التكنولوجيا في السابع إلى العاشر حصّتان متباعدتان (قرارُ الإدارة،
    #: 2026-09-02)، وهي في الحادي عشر/1 والثاني عشر/1 نصفُ زوجٍ متوازٍ مع
    #: الفنّيّة المزدوجة — والمتوازيان في خانةٍ واحدة، فشكلُهما واحد.
    #:
    #: وكان القرارُ في `Subject.requires_double_period` وحده، فلا يسع الحالين
    #: معاً: إشعالُه يُلصق حصص السابع، وإطفاؤه يفكّ زوجَ الحادي عشر.
    double_period = models.BooleanField(
        null=True,
        blank=True,
        verbose_name="حصّة مزدوجة لهذه الشعبة",
        help_text="فارغٌ = اتبع إعداد المادّة",
    )
    preferred_periods = models.JSONField(default=list, blank=True, verbose_name="حصص مفضلة")

    #: عددُ الحصص يأتي من الخطّة الدراسيّة. فإن خالفها هذا الإسنادُ لزم سببٌ
    #: يُحفظ معه — ورقمٌ يخالف الخطّةَ بلا سببٍ هو الخطأُ الذي كلّفنا سبعةَ
    #: عشرَ سجلّاً حين لم يكن للخطّة موضع.
    periods_override_reason = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="سبب مخالفة الخطّة",
        help_text="يُلزَم حين يخالف عددُ الحصص الخطّةَ الدراسيّة",
    )

    is_active = models.BooleanField(default=True, verbose_name="نشط")
    #: الحذفُ ناعمٌ ويحمل أثره: من حذف ومتى ولماذا. فإسنادٌ اختفى من الشبكة
    #: بلا أثرٍ يُقرأ بعد شهرٍ خللاً في البيانات لا قراراً اتُّخذ.
    deleted_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deleted_subject_assignments",
        verbose_name="حذفه",
    )
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الحذف")
    deletion_reason = models.CharField(
        max_length=200, blank=True, default="", verbose_name="سبب الحذف"
    )

    #: والإسنادُ أصلُ الجدول: منه يُولَّد. فلو بقي إسنادُ عامٍ مضى نشطاً وُلِّد
    #: منه جدولٌ لشُعبٍ لم تعد قائمة — فالقيدُ عليه أوجبُ منه على الحصّة.
    objects = YearScopedQuerySet.as_manager()

    class Meta:
        verbose_name = "توزيع مادة على فصل"
        verbose_name_plural = "توزيع المواد على الفصول"
        constraints = [
            #: سجلٌّ واحدٌ لكلّ معلّمٍ في المادّة والشعبة — لا أكثر.
            #:
            #: والمادّةُ في الشعبة لمعلّمٍ واحدٍ عادةً، إلّا أن تُقسَم الشعبةُ
            #: نصفين يُدرَّسان في التوقيت نفسِه بمعلّمَين (قرارُ المستخدم
            #: 2026-09-07): تكنولوجيا 11/1 وكيمياء 11/2 وفنون 12/1 وكيمياء
            #: 12/2. فحارسُ «معلّمٍ واحد» في `apply_assignment` لا في القاعدة،
            #: لأنّ القسمةَ مشروعةٌ والقاعدةُ لا تفرّق بينها وبين الخطأ.
            #:
            #: والمجموعةُ (`parallel_group`) ليست جزءاً من المفتاح: نصفا
            #: الشعبة يحملان وسمَها نفسَه ليُجدولا معاً في خانةٍ واحدة، ولو
            #: دخلت المفتاحَ لاستحال أن يتشاركاه.
            #: والمحذوفُ حذفاً ليّناً خارجَ الحساب: سجلٌّ أُبطل لا يمنع إحياءَ
            #: مثلِه، وإلّا لصار الحذفُ قفلاً على الشعبة.
            models.UniqueConstraint(
                fields=["class_group", "subject", "academic_year", "teacher"],
                condition=models.Q(is_active=True),
                name="unique_subject_per_class_year_teacher",
            )
        ]
        ordering = [
            "class_group__grade",
            "class_group__section",
            "subject__name_ar",
            "parallel_group",
        ]

    def __str__(self):
        teacher_name = self.teacher.full_name if self.teacher else "غير محدد"
        return f"{self.subject.name_ar} → {self.class_group} ({teacher_name}) [{self.weekly_periods}ح/أسبوع]"


class SchedulingResource(models.Model):
    """موردٌ محدودٌ تتنافس عليه الحصص: ملعبٌ أو معملٌ أو غرفةُ فنون.

    القيدُ ليس على المعلّم ولا على الشعبة بل على **المكان**: في المدرسة معملا
    حاسبٍ اثنان، فلا تقع أكثرُ من حصّتَي حاسبٍ في التوقيت الواحد مهما كثر
    المعلّمون. وكذلك البدنيّة: خمسةُ معلّمين وملعبان.

    ولا يُحلّ هذا بقيدٍ على المادّة وحدَها: المعملانِ يتقاسمهما «علوم الحاسب»
    و«تكنولوجيا المعلومات» معاً، فالسقفُ على المورد لا على كلّ مادّةٍ بمفردها.
    """

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="scheduling_resources",
        verbose_name="المدرسة",
    )
    name = models.CharField(max_length=100, verbose_name="المورد")
    capacity = models.PositiveIntegerField(default=1, verbose_name="كم حصّةً معاً")
    subjects = models.ManyToManyField(
        Subject, related_name="scheduling_resources", verbose_name="المواد التي تستعمله"
    )
    note = models.CharField(max_length=200, blank=True, verbose_name="ملاحظة")
    #: الملعبانِ يتقاسمهما الإعداديّ والثانويّ، لكن لا في التوقيت نفسه: حصّتا
    #: بدنيّةٍ معاً تكونان من مرحلةٍ واحدة (قرار الإدارة 2026-09-03). فالسعةُ
    #: وحدها لا تكفي — يُضاف تجانسُ المرحلة على من يشغل المورد معاً.
    same_level_only = models.BooleanField(
        default=False, verbose_name="مرحلةٌ واحدةٌ في التوقيت (لا يجتمع إعداديّ وثانويّ)"
    )
    is_active = models.BooleanField(default=True, verbose_name="نشط")

    class Meta:
        verbose_name = "مورد جدولة"
        verbose_name_plural = "موارد الجدولة"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["school", "name"], name="unique_resource_per_school")
        ]

    def __str__(self):
        return f"{self.name} ({self.capacity})"


class TeacherPreference(models.Model):
    """تفضيلات المعلم للجدولة الذكية"""

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    teacher = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="schedule_preferences",
        verbose_name="المعلّم",
    )
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="teacher_preferences", verbose_name="المدرسة"
    )
    academic_year = models.CharField(
        max_length=9, default=default_academic_year, verbose_name="العام الدراسي"
    )
    max_daily_periods = models.PositiveIntegerField(default=5, verbose_name="أقصى حصص يومية")
    max_consecutive = models.PositiveIntegerField(default=3, verbose_name="أقصى حصص متتالية")
    #: أوسعُ فراغٍ يُقبل بين حصّتين في اليوم الواحد — بعدد الحصص الفارغة.
    #:
    #: فالمعلّمُ الذي بين حصّتيه ثلاثُ فراغاتٍ يقضي يومَه في المدرسة ليعمل
    #: ساعتين. و«فراغٌ واحد» يعني أن تكون حصصُه في اليوم متباعدةً حصّةً حصّة:
    #: الثانيةُ فالرابعةُ فالسادسة — لا الثالثةُ فالسادسة.
    #:
    #: و`null` تعني «لا قيدَ شخصيّ»: يبقى الفراغُ ترجيحاً مرناً كما هو لعامّة
    #: الكادر. أمّا العددُ فقيدٌ صلبٌ في حقّ صاحبه لا يُرفع في جولة الاسترخاء.
    max_gap = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="أقصى فجوة بين حصتين",
        help_text="بعدد الحصص الفارغة — اتركه فارغاً لبقاء الفجوة ترجيحاً مرناً",
    )
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


#: كان هنا `PERSONAL_RULE_MARKERS` و`releases()`: قسمةُ التفريغات قسمين بمطابقة
#: جملةٍ عربيّةٍ («لا أولى ولا سابعة») في حقلِ السبب الحرّ. حُذفت في 2026-09-09
#: بقرار المستخدم، وقد أثبت القياسُ أنّها لا تعمل: ثلاثةٌ وتسعون تفريغاً نشطاً
#: في المدرسة، **صفرٌ** منها يطابق الجملة — وستّون منها قيودٌ شخصيّةٌ دائمةٌ في
#: المعنى (حصصُ 2·4·6) كُتب سببُها «تم». فصاحبُ القاعدة نفسُه لم يكتب الجملةَ
#: التي تُفعّلها، ومطابقةُ نصٍّ حرٍّ لا تصلح تصنيفاً.
#:
#: والقيدُ الشخصيُّ الدائمُ يُدخل من شبكة التفريغات كسائرها، ويُلغى منها.


class TeacherExemption(models.Model):
    """تفريغ معلم/منسق من حصص معينة أو يوم كامل — يُعيّنه النائب الأكاديمي"""

    objects = models.Manager()

    EXEMPTION_TYPE = [
        ("full_day", "يوم كامل"),
        ("specific_period", "حصة محددة"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="teacher_exemptions", verbose_name="المدرسة"
    )
    teacher = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="schedule_exemptions",
        verbose_name="المعلم/المنسق",
    )
    academic_year = models.CharField(
        max_length=9, default=default_academic_year, verbose_name="العام الدراسي"
    )
    exemption_type = models.CharField(
        max_length=20,
        choices=EXEMPTION_TYPE,
        verbose_name="نوع التفريغ",
    )
    day_of_week = models.IntegerField(
        choices=ScheduleSlot.DAYS,
        verbose_name="اليوم",
    )
    period_number = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="رقم الحصة (إذا حصة محددة)",
    )
    reason = models.CharField(max_length=200, verbose_name="السبب")
    #: تفريغُ يومٍ كاملٍ قرارٌ أثقلُ من مؤهّل: يُخرج المعلّمَ من الجدول يوماً في
    #: الأسبوع كلَّه. فيُسأل عن جهته — والسببُ وحدَه نصٌّ حرٌّ لا يُراجَع.
    #: (وكان يُسأل عن مرجع القرار أيضاً، فأُلغي بقرار الإدارة 2026-09-04: رقمُ
    #: التعميم لا يُعرف غالباً يومَ التفريغ، فكان يمنع الإدخالَ لا يُوثّقه.)
    #: جهاتٌ يُلزم تفريغُها الناسَ كما يُلزم المولّد. وتفريغُ «لتوليد الجدول»
    #: ليس قرارَ جهةٍ بل أداةُ تشكيلٍ: خاناتٌ تُغلق ليقع جدولُ المعلّم حيث يُراد
    #: (كقيود 2·4·6). فالمولّدُ يحترمه كسائر التفريغات — وإلّا فما فائدتُه —
    #: لكنّ البديلَ والتبديلَ يجوز فيه، لأنّ صاحبَه لم يُمنَع من الحصّة، بل
    #: رُتّب له جدولُه (قرارُ المستخدم 2026-09-11).
    SOFT_SOURCES = frozenset({"generation"})

    source = models.CharField(
        max_length=12,
        choices=[
            ("ministry", "قرارُ الوزارة"),
            ("school", "قرارُ إدارة المدرسة"),
            ("department", "قرارُ القسم الأكاديميّ"),
            ("generation", "لتوليد الجدول"),
            ("other", "أخرى"),
        ],
        default="school",
        verbose_name="جهة القرار",
    )

    @property
    def binds_people(self) -> bool:
        """أيمنع هذا التفريغُ إشغالَ صاحبه بديلاً أو تبديلَه فيه؟

        قرارُ الوزارة والإدارة والقسم يمنعان؛ و«لتوليد الجدول» يُوسَم ولا يمنع.
        """
        return self.source not in self.SOFT_SOURCES

    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        verbose_name="أنشئ بواسطة",
    )
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "تفريغ معلم"
        verbose_name_plural = "تفريغات المعلمين"
        ordering = ["day_of_week", "period_number"]

    def __str__(self):
        day_name = dict(ScheduleSlot.DAYS).get(self.day_of_week, "")
        if self.exemption_type == "full_day":
            return f"تفريغ {self.teacher.full_name} — {day_name} (يوم كامل)"
        return f"تفريغ {self.teacher.full_name} — {day_name} ح{self.period_number}"

    def clean(self):
        """الحصّةُ المحدّدةُ لا تُقبل بلا رقم.

        ولا يمسّ هذا النصابَ في شيء: التفريغُ يقول *متى لا يُجدَّل*، والنصابُ
        يقول *كم يُدرّس*. فمن فُرّغ يومَ الأحد يُحشر نصابُه في بقيّة الأيّام،
        وإن خُفّف فبقرارٍ آخر.
        """
        super().clean()
        from django.core.exceptions import ValidationError

        if self.exemption_type == "specific_period" and not self.period_number:
            raise ValidationError({"period_number": "تفريغُ حصّةٍ بعينها يحتاج رقمَها."})


class ScheduleBaseline(models.Model):
    """أساسٌ مرجعيٌّ لمؤشرات الجودة: لقطةُ مؤشرات جدولٍ بعينه باسمٍ وتاريخ.

    كلُّ توليدٍ بعده يُعرض بفرقه عن هذا الأساس، وإن تغيّر الجدولُ الحيُّ لاحقاً —
    فالمقارنةُ بمرجعٍ ثابتٍ لا بهدفٍ يتحرّك (بند 25 من خطّة التجويد 2026-09-04).
    """

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="schedule_baselines", verbose_name="المدرسة"
    )
    academic_year = models.CharField(max_length=9, verbose_name="العام الدراسي")
    label = models.CharField(max_length=60, verbose_name="الاسم")
    metrics = models.JSONField(default=dict, verbose_name="المؤشرات")

    #: المرجعُ المعتمَد الذي تُنسَب إليه الدرجةُ المعروضة — واحدٌ لكلّ عامٍ ومدرسة.
    #:
    #: وبلا هذه الرايةِ كان المرجعُ «آخرَ أساسٍ محفوظ»، فأيُّ ضغطةٍ على «حفظ
    #: أساس» في شاشة المختبر تُحرّكه. ومرجعٌ يتحرّك مع كلّ توليدٍ سقّاطةٌ تقول
    #: مئةً دائماً: كلُّ جدولٍ يُقاس بنفسه فيبدو كاملاً. فالتثبيتُ قرارٌ يُتَّخذ
    #: مرّةً ويُراجَع سنويّاً، لا أثرٌ جانبيٌّ لضغطة زرّ.
    is_pinned = models.BooleanField(default=False, verbose_name="مرجعٌ معتمَد")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="أنشأه",
    )

    class Meta:
        verbose_name = "أساس مرجعي للجدول"
        verbose_name_plural = "الأسس المرجعية للجدول"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "academic_year", "label"], name="unique_schedule_baseline"
            ),
            # مرجعان معتمَدان لعامٍ واحدٍ يجعلان الدرجةَ تابعةً لترتيب الصفوف.
            models.UniqueConstraint(
                fields=["school", "academic_year"],
                condition=models.Q(is_pinned=True),
                name="one_pinned_baseline_per_year",
            ),
        ]

    def __str__(self):
        return f"{self.label} — {self.academic_year}"


class ScheduleConstraintOverride(models.Model):
    """انحرافٌ متعمَّدٌ عن قيدٍ عرّفته الشيفرة — والصفوفُ استثناءاتٌ لا سجلّ.

    صفرُ صفوفٍ هنا يعني «افتراضُ الكود بالضبط»، فلا بذرةَ تُزرع ولا انحرافَ
    يقع بين قاعدة الإنتاج وقاعدة التطوير ولا أمرَ مزامنةٍ يُصان. وقيدٌ جديدٌ
    يُنشَر بافتراضه ولا يحتاج هجرةَ بيانات.

    والصفُّ يحمل أحدَ أمرين بحسب نوع القيد: **رتبةَ الكسر** للصلب — متى يتنازل
    إن ضاق الجدول — أو **الوزنَ** للمرن. وقيودُ النواة لا تُحرَّر بحال؛ يحرسها
    `ConstraintSpec.tunable` في السجلّ و`clean()` هنا.

    راجع `operations.constraint_registry`.
    """

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="constraint_overrides",
        verbose_name="المدرسة",
    )
    academic_year = models.CharField(
        max_length=9, default=default_academic_year, verbose_name="العام الدراسي"
    )
    code = models.CharField(max_length=20, verbose_name="رمز القيد")
    break_at = models.CharField(
        max_length=10,
        blank=True,
        default="",
        verbose_name="متى يُكسَر",
        help_text="للقيود الصلبة — فارغٌ يعني افتراضَ الكود",
    )
    weight = models.FloatField(
        null=True,
        blank=True,
        verbose_name="الوزن",
        help_text="للقيود المرنة — فارغٌ يعني افتراضَ الكود",
    )
    #: لماذا خُولف الافتراض — فانحرافٌ بلا سببٍ يُقرأ بعد شهرٍ خللاً لا قراراً.
    reason = models.CharField(max_length=200, verbose_name="سبب المخالفة")
    updated_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="عدّله",
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التعديل")

    class Meta:
        verbose_name = "استثناء قيد جدول"
        verbose_name_plural = "استثناءات قيود الجدول"
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "academic_year", "code"], name="unique_constraint_override"
            )
        ]

    def __str__(self):
        from ..constraint_registry import spec

        found = spec(self.code)
        title = found.title if found else self.code
        return f"{self.code} · {title} — {self.academic_year}"

    def clean(self):
        from django.core.exceptions import ValidationError

        from ..constraint_registry import BREAK_CHOICES, HARD, SOFT, spec

        found = spec(self.code)
        if found is None:
            raise ValidationError({"code": "رمزٌ لا يعرفه سجلُّ القيود."})
        if not found.tunable:
            raise ValidationError(
                {"code": f"«{found.title}» من النواة — لا يُحرَّر: خرقُه يُنتج جدولاً مستحيلاً."}
            )
        if found.kind == HARD:
            if self.break_at not in dict(BREAK_CHOICES):
                raise ValidationError({"break_at": "رتبةٌ غيرُ معروفة."})
            if self.weight is not None:
                raise ValidationError({"weight": "الوزنُ للقيود المرنة وحدَها."})
        if found.kind == SOFT:
            if self.weight is None:
                raise ValidationError({"weight": "القيدُ المرنُ يُعايَر بوزنه."})
            if self.break_at:
                raise ValidationError({"break_at": "الرتبةُ للقيود الصلبة وحدَها."})


class ScheduleGenerationQuerySet(models.QuerySet):
    """حذفُ التوليدات — بحارسٍ يعمل على الدفعة كما على الصفّ.

    حذفُ توليدٍ معتمَد من لوحة الإدارة كان يمرّ بلا اعتراض، وحقلُ `generation`
    على الحصّة `SET_NULL`: فيفقد الجدولُ الحيّ نسبَه إلى توليده، ويصير — إن
    أُطفئ يوماً — ركاماً في عين `prune_schedule_slots`. وقع هذا فعلاً في
    2026-09-05 أثناء العمل.

    فالقاعدة: **توليدٌ له حصّةٌ حيّةٌ لا يُحذف** — والمعتمَدُ لا يُحذف بحالته
    ولو خلت حصصُه. وما يُحذف يأخذ حصصَه الميّتة معه، فلا يُخلّف يتامى.
    """

    def delete(self):
        protected = list(
            self.filter(models.Q(status="approved") | models.Q(slots__is_active=True)).distinct()
        )
        if protected:
            raise models.ProtectedError(
                "توليدٌ معتمَدٌ أو له حصصٌ حيّة لا يُحذف — اعتمد مسودّةً أخرى بدله.",
                set(protected),
            )
        ScheduleSlot.objects.filter(generation__in=self).delete()
        return super().delete()


class ScheduleGeneration(models.Model):
    """سجل عمليات التوليد التلقائي للجدول.

    والحالاتُ تبدأ قبل النتيجة لا بعدها: التوليدُ يستغرق دقائق، فلا يجوز أن
    يكون أوّلَ أثرٍ له صفٌّ يظهر عند نجاحه. فالصفُّ يُنشأ «في الانتظار» عند
    الضغط، ويصير «قيد التوليد» حين يلتقطه العامل، ثمّ «مسودّة» أو «فشل».
    وبهذا يرى المستخدمُ ما يجري، ويعرف النظامُ أنّ توليداً جارياً فلا يُشغّل
    ثانياً فوقه.
    """

    #: الحالاتُ العابرة — لا نتيجةَ لها بعد، ولا تُحسب جدولاً.
    PENDING_STATUSES = ("queued", "running")

    STATUS = [
        ("queued", "في الانتظار"),
        ("running", "قيد التوليد"),
        ("draft", "مسودة"),
        ("approved", "معتمد"),
        ("archived", "مؤرشف"),
        ("failed", "فشل"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="schedule_generations",
        verbose_name="المدرسة",
    )
    academic_year = models.CharField(max_length=9, verbose_name="العام الدراسي")
    generated_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, verbose_name="ولّده"
    )
    generated_at = models.DateTimeField(auto_now_add=True, verbose_name="وقت التوليد")
    status = models.CharField(max_length=10, choices=STATUS, default="draft", verbose_name="الحالة")
    quality_score = models.FloatField(default=0, verbose_name="نقاط الجودة (0-100)")
    hard_violations = models.IntegerField(default=0, verbose_name="انتهاكات صلبة")
    soft_violations = models.JSONField(default=dict, verbose_name="انتهاكات مرنة")
    total_slots_created = models.IntegerField(default=0, verbose_name="الحصص المولَّدة")
    generation_time_ms = models.IntegerField(default=0, verbose_name="زمن التوليد (مللي ثانية)")
    config_snapshot = models.JSONField(default=dict, verbose_name="نسخة الإعدادات")
    #: مؤشراتُ مختبر الجودة (`operations.schedule_lab`) — تُحسب عند انتهاء التوليد
    #: وعند الاعتماد، وتُعرض بجانب الأساس المرجعيّ لا رقماً مجرَّداً.
    metrics = models.JSONField(default=dict, blank=True, verbose_name="مؤشرات الجودة")
    #: متى انتهى — لا يُقاس من `generated_at` لأنّ الانتظارَ في الطابور ليس توليداً.
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="انتهى في")
    #: سببُ الفشل كما يُقال للمستخدم — وصمتُ الفشل أسوأُ من الفشل.
    error_message = models.TextField(blank=True, verbose_name="سبب الفشل")

    class Meta:
        verbose_name = "عملية توليد جدول"
        verbose_name_plural = "عمليات توليد الجدول"
        ordering = ["-generated_at"]
        indexes = [
            models.Index(
                fields=["school", "academic_year", "status"],
                name="schedgen_school_year_stat",
            ),
        ]

    objects = ScheduleGenerationQuerySet.as_manager()

    def __str__(self):
        return (
            f"توليد {self.academic_year} — {self.get_status_display()} ({self.quality_score:.0f}%)"
        )

    @property
    def is_pending(self):
        return self.status in self.PENDING_STATUSES

    @property
    def is_protected(self) -> bool:
        """لا يُحذف: معتمَدٌ، أو له حصّةٌ حيّةٌ بأيّ حال."""
        return self.status == "approved" or self.slots.filter(is_active=True).exists()

    def delete(self, *args, **kwargs):
        """يرفض حذفَ المحميّ، ويأخذ الحصصَ الميّتةَ مع غيره — راجع `ScheduleGenerationQuerySet`."""
        if self.is_protected:
            raise models.ProtectedError(
                "توليدٌ معتمَدٌ أو له حصصٌ حيّة لا يُحذف — اعتمد مسودّةً أخرى بدله.",
                {self},
            )
        self.slots.all().delete()
        return super().delete(*args, **kwargs)


class FreeSlotRegistry(models.Model):
    """
    سجل الحصص الحرة لكل معلم — يُبنى تلقائياً من فراغات ScheduleSlot.
    يُستخدم لتسهيل البحث عن بديل أو وقت تعويض.
    """

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    teacher = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="free_slots",
        verbose_name="المعلم",
    )
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="free_slots", verbose_name="المدرسة"
    )
    day_of_week = models.IntegerField(choices=ScheduleSlot.DAYS, verbose_name="اليوم")
    period_number = models.IntegerField(verbose_name="رقم الحصة")
    academic_year = models.CharField(
        max_length=9, default=default_academic_year, verbose_name="العام الدراسي"
    )
    is_available = models.BooleanField(
        default=True,
        verbose_name="متاح؟",
        help_text="False = محجوز مؤقتاً (تعويض أو مهمة)",
    )
    reserved_for = models.ForeignKey(
        "CompensatorySession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reserved_slots",
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
