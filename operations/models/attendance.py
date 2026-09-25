"""الحصص وحضورُ الطلبة: الحصّةُ المنفَّذة، والحضورُ بالحصّة، والأعذارُ، وتواصلُ وليّ الأمر، وتنبيهاتُ الغياب، وتأكيدُ اليوم والحصّة، وخروجُ الطالب."""

import uuid

from django.db import models
from django.utils import timezone

from core.models import ClassGroup, CustomUser, School
from core.validators import FileTypeValidator

from .common import _uuid
from .schedule import Subject


def _excuse_upload_path(instance, filename):
    """F-006: مسار رفع غير متوقع — UUID بدل اسم الملف الأصلي."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"tardiness_excuses/{uuid.uuid4().hex}.{ext}"


class Session(models.Model):
    STATUS = [
        ("scheduled", "مجدولة"),
        ("in_progress", "جارية"),
        ("completed", "مكتملة"),
        ("cancelled", "ملغاة"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="sessions", verbose_name="المدرسة"
    )
    class_group = models.ForeignKey(
        ClassGroup, on_delete=models.CASCADE, related_name="sessions", verbose_name="الشعبة"
    )
    teacher = models.ForeignKey(
        CustomUser, on_delete=models.PROTECT, related_name="sessions", verbose_name="المعلم"
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
        verbose_name="المادّة",
    )
    date = models.DateField(verbose_name="التاريخ", db_index=True)
    start_time = models.TimeField(verbose_name="وقت البدء")
    end_time = models.TimeField(verbose_name="وقت النهاية")
    #: رقمُ الحصّة في الجدول المعتمد — فارغٌ لما سبق الحقلَ ولا خانةَ نشطةً تطابقه.
    period_number = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="الحصّة")
    status = models.CharField(
        max_length=15, choices=STATUS, default="scheduled", db_index=True, verbose_name="الحالة"
    )
    #: تُورَّث من `ScheduleSlot.elective_group`: شعبةٌ تتفرّق بين مادّتين في
    #: التوقيت نفسه تحتاج جلستين بمعلّمَين، والقيدُ الفريد بلا هذا الحقل كان
    #: يُسقط الثانيةَ بصمت في `bulk_create(ignore_conflicts=True)`.
    elective_group = models.CharField(
        max_length=40, blank=True, default="", verbose_name="مجموعة الاختيار"
    )
    #: صاحبُ الحصّة قبل التبديل — ووجودُه هو ما يقول إنّها مبدَّلة.
    #:
    #: التبديلُ يقع على يومٍ بعينه لا على قالب الأسبوع، فأثرُه يُكتب هنا لا في
    #: `ScheduleSlot`. ومن نظر إلى جدول اليوم رأى المبدَّلةَ بلونها ورأى من
    #: كانت له — ولو خُزّن المعلّمُ الجديدُ وحدَه لما عرف أحدٌ أنّ شيئاً جرى.
    original_teacher = models.ForeignKey(
        CustomUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sessions_swapped_away",
        verbose_name="المعلّم الأصليّ",
    )
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

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
                fields=["class_group", "date", "start_time", "elective_group"],
                name="no_class_time_overlap",
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
    #: أين الطالب — لا حالتُه. راجع الحقلَ `whereabouts`.
    WHEREABOUTS = [
        ("clinic", "في العيادة"),
        ("activity", "في نشاطٍ مدرسيّ"),
        ("out_permit", "خرج بإذن"),
        ("out_no_permit", "خرج دون إذن"),
        ("left_early", "استئذانٌ مبكّر"),
        ("gate", "عند البوّابة (وصولٌ متأخّر)"),
    ]

    #: من سجّل — راجع الحقلَ `source`.
    SOURCES = [
        ("teacher", "معلّم الحصّة"),
        ("supervisor", "مشرف الجناح"),
        ("gate", "ملاحظ الطلبة"),
        ("clinic", "العيادة"),
        ("system", "النظام"),
        #: نقرةُ المعلّم «دخل متأخّراً» (قرارُ 2026-09-13): المعلّمُ لا يرصد الغياب،
        #: لكنّه يرى من دخل متأخّراً قبل وصول المشرف. النظامُ يسجّل لحظةَ النقرة،
        #: والمشرفُ يجدها في كشفه ويثبّتها.
        ("teacher_late", "نقرةُ المعلّم — دخل متأخّراً"),
        #: خرج بإذن المعلّم ولم يعد حتى نهاية الحصّة (`operations/class_exit.py`).
        ("teacher_out", "نقرةُ المعلّم — خرج بإذنٍ ولم يعد"),
    ]

    #: الأعذارُ المقبولة — القائمةُ المغلقةُ في الدليل التنظيميّ 2026 (م 3.4.1.4، ص29):
    #: خمسةٌ لا يزيدها اجتهاد، «وكلُّ ما عدا ذلك غيابٌ بدون عذر». و«أخرى» بقيّةٌ من
    #: قبل القائمة تُقرأ ولا تُختار (`operations/excuses.py`).
    EXCUSE = [
        ("medical", "مرضٌ بتقريرٍ طبّيّ"),
        ("bereavement", "وفاةٌ في القرابة الأولى"),
        ("family", "ظرفٌ عائليٌّ طارئٌ بكتابٍ رسميّ"),
        ("state_representation", "تمثيلُ الدولة في لقاءٍ خارجيّ"),
        ("official", "موعدُ محكمةٍ أو هيئةٍ حكوميّة، أو مقابلةٌ للثاني عشر"),
        ("other", "أخرى (قبل القائمة المغلقة)"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    session = models.ForeignKey(
        Session, on_delete=models.CASCADE, related_name="attendances", verbose_name="الحصّة"
    )
    student = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="attendances", verbose_name="الطالب"
    )
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="attendances", verbose_name="المدرسة"
    )
    status = models.CharField(
        max_length=10, choices=STATUS, default="present", db_index=True, verbose_name="الحالة"
    )
    tardiness_minutes = models.PositiveSmallIntegerField(
        verbose_name="دقائق التأخير",
        null=True,
        blank=True,
        help_text="عدد دقائق التأخير الصباحي (يُسجَّل فقط عند status=late)",
    )
    tardiness_recorded_at = models.DateTimeField(
        verbose_name="توقيت تسجيل التأخير",
        null=True,
        blank=True,
    )
    #: **أين الطالب** — حقلٌ مستقلٌّ عن `status` (قرارُ المستخدم 2026-09-12، §0.12).
    #:
    #: محاكاةُ يومٍ دراسيٍّ أنتجت سبعَ حالاتٍ و`status` يحمل أربعاً. فالطالبُ
    #: في العيادة ليس حاضراً في فصله وليس غائباً عن مدرسته، والطالبُ في
    #: مسابقةٍ مدرسيّةٍ **حاضرٌ في عهدة المدرسة** — وقائمةُ الأعذار في م
    #: 3.4.1.4 **مغلقةٌ** لا يدخلها نشاطٌ تنظّمه المدرسة. والهاربُ غائبٌ
    #: بمخالفةٍ لا كمن لم يأتِ أصلاً.
    #:
    #: فالحقيقةُ ثلاثيّة: حاضرٌ؟ · أين؟ · لماذا؟ و`status` وحدَها تكذب في
    #: ثلاثٍ من سبع. والحدُّ الفاصلُ في النشاط: **هل خرج من عهدة المدرسة؟**
    whereabouts = models.CharField(
        max_length=14,
        choices=WHEREABOUTS,
        blank=True,
        verbose_name="مكانُ الطالب",
        help_text="فارغٌ = في فصله. وما سواه سببُ غيابه عن الفصل لا عن المدرسة",
    )
    #: من سجّل هذه الحالة — والحقبتان لا تُخلطان في إحصاء.
    #:
    #: قبل 2026-09 كان الرصدُ بيد معلّم الحصّة، وصار بيد مشرف الجناح (قرارُ
    #: المدير). فسجلّاتُ الحقبتين تختلف مصدراً لا شكلاً، وإحصاءٌ يخلطهما
    #: يقارن ما لا يُقارن. وفي أسبوع التشغيل الموازي **يرصد الاثنان معاً**،
    #: فبلا هذا الحقل لا يُعرف أيُّ رقمٍ لأيّهما.
    source = models.CharField(
        max_length=12, choices=SOURCES, default="teacher", db_index=True, verbose_name="المصدر"
    )
    #: دقائقُ التأخّر عن بدء الحصّة — تُكتب مع حالة «متأخّر» وحدَها.
    #:
    #: والعدُّ مرّاتٍ وحدَه يسوّي بين من دخل بعد ست دقائق ومن دخل بعد ثلاثين،
    #: والدقائقُ الضائعةُ هي ما يُقارَن لاحقاً بتحصيل الطالب في المادّة (طلبُ
    #: المستخدم 2026-09-13). وفارغٌ يعني «لم تُقَس» لا «صفر».
    late_minutes = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="دقائقُ التأخّر عن الحصّة"
    )
    excuse_type = models.CharField(
        max_length=20, choices=EXCUSE, blank=True, verbose_name="نوع العذر"
    )
    #: العذرُ الذي غطّى هذا الغياب — قرارٌ واحدٌ بمستنده يغطّي أيّاماً وحصصاً
    #: (`AbsenceExcuse`). و`excuse_type` يبقى مكتوباً على الصفّ لأنّ الحسابَ يقرؤه.
    excuse = models.ForeignKey(
        "operations.AbsenceExcuse",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rows",
        verbose_name="العذرُ المقبول",
    )
    excuse_notes = models.TextField(blank=True, verbose_name="بيان العذر")
    excuse_file = models.FileField(
        upload_to=_excuse_upload_path,
        blank=True,
        verbose_name="ملف إذن ولي الأمر",
        validators=[FileTypeValidator(allowed_types="excuse", max_size_mb=10)],
    )
    #: الخروجُ بإذن المعلّم الذي **يحسبه** هذا الرصد (قرارُ 2026-09-16) — أثرُ المصدر.
    #:
    #: يُكتب حين رأى المشرفُ الخروجَ في كشفه فثبّته غائباً أو بدّله، أو حين أنهاه النظامُ
    #: بنهاية الحصّة. وبه يُعرف أنّ الغيابَ مشتقٌّ من الخروج: فيُرجَع حاضراً إن عاد
    #: الطالبُ قبل الجرس، ولا يُقلب ثانيةً ما حسمه المشرفُ وهو يرى الخروج. وفارغٌ =
    #: رصدٌ لم يرَ خروجاً — غيابٌ قاله المشرفُ بنفسه لا يُمسّ.
    #:
    #: بلا فهرسٍ كامل (أكثرُ السطور فارغة)، وبفهرسٍ جزئيٍّ على غير الفارغ في `Meta`: حذفُ
    #: خروجٍ (إلغاءُ المعلّم) يُفرغ هذا العمودَ ويفحصه قيدُ المفتاح — وبلا فهرسٍ يمسحان
    #: أكبرَ جداول التشغيل كلَّه في كلّ نقرة.
    exit = models.ForeignKey(
        "operations.ClassExit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=False,
        related_name="accounted_attendances",
        verbose_name="الخروجُ المحسوب",
    )
    marked_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="marked_attendances",
        verbose_name="رصده",
    )
    marked_at = models.DateTimeField(auto_now_add=True, verbose_name="وقت الرصد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التعديل")

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
            models.Index(
                fields=["exit"],
                name="attendance_exit_accounted",
                condition=models.Q(exit__isnull=False),
            ),
        ]

    def __str__(self):
        return f"{self.student.full_name} | {self.get_status_display()} | {self.session}"


class AbsenceExcuse(models.Model):
    """عذرٌ لغياب طالبٍ في مدّة — قرارُ المشرف في المهلة، أو طلبٌ ينتظر النائبَ بعدها.

    الدليلُ التنظيميّ 2026: القائمةُ مغلقةٌ بخمسة (م 3.4.1.4)، والتقريرُ الطبّيّ خلال
    يومين من العودة. وقرارُ 2026-09-14: المهلةُ يومان دراسيّان **من عودة الطالب**،
    وبعدها «أرسل للنائب» — فيُحفظ العذرُ «بانتظار النائب» ولا يمسّ الصفوفَ حتى يقبله.
    القرارُ واحدٌ يغطّي كلَّ حصص الغياب في مدّته، ومستندُه واحدٌ لا يُنسخ على الصفوف.
    """

    KINDS = [k for k in StudentAttendance.EXCUSE if k[0] != "other"]
    STATUSES = [
        ("accepted", "مقبول"),
        ("pending", "بانتظار النائب الإداريّ"),
        ("rejected", "مرفوض"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="absence_excuses", verbose_name="المدرسة"
    )
    student = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="absence_excuses", verbose_name="الطالب"
    )
    date_from = models.DateField(verbose_name="من")
    date_to = models.DateField(verbose_name="إلى")
    kind = models.CharField(max_length=20, choices=KINDS, verbose_name="نوعُ العذر")
    notes = models.TextField(blank=True, verbose_name="بيان")
    document = models.FileField(
        upload_to=_excuse_upload_path,
        blank=True,
        verbose_name="المستند",
        validators=[FileTypeValidator(allowed_types="excuse", max_size_mb=10)],  # type: ignore[no-untyped-call]
    )
    granted_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="absence_excuses_granted",
        verbose_name="سجّل العذر",
    )
    granted_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ التسجيل")
    #: قُبل بعد مهلة اليومين — بصلاحيّة النائب وبسببٍ مكتوب.
    after_deadline = models.BooleanField(default=False, verbose_name="بعد انقضاء المهلة")
    override_reason = models.TextField(blank=True, verbose_name="سببُ القبول بعد المهلة")
    #: «مقبول» يُكتب على الصفوف؛ «بانتظار النائب» و«مرفوض» لا يمسّانها.
    status = models.CharField(
        max_length=10,
        choices=STATUSES,
        default="accepted",
        db_default="accepted",
        db_index=True,
        verbose_name="الحالة",
    )
    reviewed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="absence_excuses_reviewed",
        verbose_name="قرّره النائب",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ قرار النائب")
    rejection_reason = models.TextField(
        blank=True, default="", db_default="", verbose_name="سببُ الرفض"
    )

    class Meta:
        verbose_name = "عذرُ غياب"
        verbose_name_plural = "أعذارُ الغياب"
        ordering = ["-date_from"]
        indexes = [
            models.Index(fields=["school", "student"]),
            models.Index(fields=["student", "date_from"]),
        ]

    def __str__(self) -> str:
        return f"{self.student.full_name} | {self.get_kind_display()} | {self.date_from}–{self.date_to}"


class GuardianContact(models.Model):
    """إخطارُ وليّ الأمر بغياب ابنه — من اتّصل ومتى وعن أيّ يومٍ وبمَ أُجيب.

    الدليلُ 2026 م 3.4.1.5: الإخطارُ في اليوم نفسِه هاتفيّاً ونصّيّاً، ومهلةُ الردّ
    يومان **من الإخطار** (قرارُ 2026-09-13). حقيقةٌ تُكتب ولا تُحذف.
    """

    OUTCOMES = [
        ("answered", "ردّ"),
        ("no_answer", "لم يردّ"),
        ("will_excuse", "سيُحضر عذراً"),
    ]
    CHANNELS = [("phone", "هاتف"), ("sms", "رسالة نصّيّة")]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="guardian_contacts", verbose_name="المدرسة"
    )
    student = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="guardian_contacts",
        verbose_name="الطالب",
    )
    absence_date = models.DateField(verbose_name="يومُ الغياب")
    outcome = models.CharField(max_length=12, choices=OUTCOMES, verbose_name="النتيجة")
    channel = models.CharField(
        max_length=6, choices=CHANNELS, default="phone", verbose_name="وسيلة التواصل"
    )
    note = models.CharField(max_length=200, blank=True, verbose_name="ملاحظة")
    contacted_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="guardian_contacts_made",
        verbose_name="القائم بالتواصل",
    )
    contacted_at = models.DateTimeField(verbose_name="وقتُ الاتّصال")

    class Meta:
        verbose_name = "إخطارُ وليّ أمر"
        verbose_name_plural = "إخطاراتُ أولياء الأمور"
        ordering = ["-contacted_at"]
        indexes = [
            models.Index(fields=["school", "student"]),
            models.Index(fields=["student", "absence_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.student.full_name} | {self.absence_date} | {self.get_outcome_display()}"


class AbsenceAlert(models.Model):
    STATUS = [
        ("pending", "قيد المراجعة"),
        ("notified", "تم الإبلاغ"),
        ("resolved", "تم الحل"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, verbose_name="المدرسة")
    student = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="absence_alerts", verbose_name="الطالب"
    )
    absence_count = models.IntegerField(verbose_name="عدد أيّام الغياب")
    #: مفتاح العتبة في «سياسة تقييم الطلبة» — تنبيهٌ واحد لكل عتبةٍ في العام.
    #: كان التنبيه واحداً للعام كلّه، فلا يُنذَر أحدٌ عند العتبات التالية.
    gate = models.CharField(max_length=20, blank=True, verbose_name="العتبة")
    period_start = models.DateField(verbose_name="بداية الفترة")
    period_end = models.DateField(verbose_name="نهاية الفترة")
    status = models.CharField(
        max_length=10, choices=STATUS, default="pending", db_index=True, verbose_name="الحالة"
    )
    created_at = models.DateTimeField(
        auto_now_add=True, db_index=True, verbose_name="تاريخ الإنشاء"
    )
    resolved_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_alerts",
        verbose_name="عالجه",
    )

    class Meta:
        verbose_name = "تنبيه غياب"
        verbose_name_plural = "تنبيهات الغياب"
        ordering = ["-created_at"]

    def __str__(self):
        return f"تنبيه: {self.student.full_name} | {self.absence_count} يوم"


class SectionDayConfirmation(models.Model):
    """تثبيتُ مشرفِ الجناح رصدَ شعبةٍ في يوم — و**لا حضورَ افتراضيّاً**.

    بلا هذا السجلّ لا يُفرَّق بين «شعبةٍ كلُّها حاضرة» و«شعبةٍ لم تُرصد» —
    فالقاعدةُ في الحالين خاليةٌ من غياب. والفرقُ بينهما هو الفرقُ بين يومٍ
    نظيفٍ ويومٍ مفقود، وبين مشرفٍ أنهى عمله ومشرفٍ لم يبدأه.

    ومنه يُشتقّ «شُعبي المتبقّية n/5» الذي يراه المشرفُ صباحاً، وتنبيهُ
    القيادة إن مضت الحصّةُ الثانيةُ وشعبةٌ لم تُرصد.

    والعددان محفوظان لا محسوبان: يُقرآن في تقرير الوزارة بعد الحصّة الثانية
    ثمّ تتبدّل الحالاتُ باعتماد الأعذار — فلو حُسبا وقتَ القراءة لأخرج
    التقريرُ رقماً غيرَ الذي رُفع.
    """

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="day_confirmations", verbose_name="المدرسة"
    )
    class_group = models.ForeignKey(
        ClassGroup,
        on_delete=models.CASCADE,
        related_name="day_confirmations",
        verbose_name="الشعبة",
    )
    date = models.DateField(db_index=True, verbose_name="التاريخ")
    confirmed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="day_confirmations",
        verbose_name="أكّده",
    )
    confirmed_at = models.DateTimeField(auto_now=True, verbose_name="وقت التأكيد")
    present_count = models.PositiveSmallIntegerField(default=0, verbose_name="الحاضرون")
    absent_count = models.PositiveSmallIntegerField(default=0, verbose_name="الغائبون")
    late_count = models.PositiveSmallIntegerField(default=0, verbose_name="المتأخّرون")
    #: كم حصّةً كُتبت فيها الحالة — برهانُ السريان لا ادّعاؤه.
    periods_written = models.PositiveSmallIntegerField(default=0, verbose_name="الحصص المرصودة")
    note = models.TextField(blank=True, verbose_name="ملاحظة")

    class Meta:
        verbose_name = "تثبيتُ رصدِ شعبة"
        verbose_name_plural = "تثبيتاتُ رصد الشُّعب"
        ordering = ["-date", "class_group"]
        constraints = [
            models.UniqueConstraint(
                fields=["class_group", "date"], name="unique_section_day_confirmation"
            )
        ]
        indexes = [models.Index(fields=["school", "date"])]

    def __str__(self):
        return f"{self.class_group.short_code} · {self.date} · غياب {self.absent_count}"


class ClassExit(models.Model):
    """خروجُ طالبٍ من الفصل بإذن المعلّم أثناء الحصّة — ومتى عاد.

    المعلّمُ يملك إذنَ الخروج من **الفصل** لا من المدرسة (الدليل 2026، 3.4.3: الخروجُ
    من المدرسة بحضور وليّ الأمر ببطاقته). والخروجُ بلا استئذانٍ مخالفة 1-02، و«عدمُ
    العودة بعد استئذانه» هروبٌ من الحصّة (تعريفات ص6). فالسجلُّ يحمل ما يفرّق الثلاثة:
    خرج بإذن، ومتى، وهل عاد ومتى.

    سطرٌ لكلّ خروج — فالطالبُ قد يخرج مرّتين في الحصّة، وسجلُّ الحضور سطرٌ واحدٌ
    لكلّ طالبٍ في الحصّة لا يحمل ذلك. ومنه عدّادا الخروج بالمادّة (مرّاتٍ ودقائق)
    و«دقائقُ الحضور الفعليّ» التي تُقارَن بالتحصيل (قرارُ 2026-09-13).
    """

    DESTINATIONS = [
        ("clinic", "العيادة"),
        ("admin", "الإدارة / المشرف"),
        ("restroom", "دورة المياه"),
        ("other", "أخرى"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="class_exits", verbose_name="المدرسة"
    )
    session = models.ForeignKey(
        Session, on_delete=models.CASCADE, related_name="class_exits", verbose_name="الحصّة"
    )
    student = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="class_exits", verbose_name="الطالب"
    )
    destination = models.CharField(
        max_length=10, choices=DESTINATIONS, default="restroom", verbose_name="الوجهة"
    )
    left_at = models.DateTimeField(verbose_name="وقتُ الخروج")
    returned_at = models.DateTimeField(null=True, blank=True, verbose_name="وقتُ العودة")
    allowed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="class_exits_allowed",
        verbose_name="أذِن به",
    )

    class Meta:
        verbose_name = "خروجٌ من الفصل"
        verbose_name_plural = "خروجٌ من الفصل"
        ordering = ["-left_at"]
        indexes = [
            models.Index(fields=["school", "session"]),
            models.Index(fields=["student", "left_at"]),
        ]

    @property
    def is_out(self) -> bool:
        return self.returned_at is None

    def minutes_away(self, until=None) -> int:
        """دقائقُ الغياب عن الفصل — حتى العودة، أو حتى `until` (نهايةُ الحصّة) لمن لم يعد."""
        end = self.returned_at or until
        if end is None:
            return 0
        return max(0, int((end - self.left_at).total_seconds() // 60))

    def __str__(self):
        return f"{self.student.full_name} · {self.get_destination_display()} · {self.left_at:%H:%M}"


class PeriodConfirmation(models.Model):
    """تثبيتُ مشرف الجناح رصدَ **حصّةٍ** لشعبة — لا يومِها.

    المشرفُ يدخل الفصلَ في كلّ حصّة (قرارُ 2026-09-13): الأولى قبل نهايتها،
    والبقيّةَ في بدايتها. فالتثبيتُ لكلّ خانةٍ زمنيّة، ومنه تُشتقّ نقاطُ الحصص على
    بطاقة الشعبة، و«الفائتة» التي لم تُثبَّت حتى خمس دقائق بعد نهايتها
    (`PERIOD_RECORDING_GRACE_MINUTES`) — ومحاسبتُها للنائب الإداريّ.

    والخانةُ لا الحصّة: زوجُ الاختيار حصّتان في خانةٍ واحدة، يُثبَّتان معاً.

    ووقتان لا وقتٌ واحد: `first_confirmed_at` لحظةُ أوّل تثبيتٍ ولا يتغيّر بعدها،
    و`confirmed_at` آخرُ تثبيت. والحصّةُ التي ثُبّتت أوّلَ مرّةٍ بعد مهلتها تبقى
    `confirmed_late` ولو ثُبّتت ثانيةً (قرارُ 2026-09-13) — فالتثبيتُ المتأخّر لا يمحو
    أثرَ التأخير من تقرير النائب الإداريّ.

    ولا نسخَ من حصّةٍ إلى أخرى: أُزيل الزرُّ بقرار 2026-09-13 — كلُّ حصّةٍ دخولٌ إلى الفصل.
    """

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="period_confirmations",
        verbose_name="المدرسة",
    )
    class_group = models.ForeignKey(
        ClassGroup,
        on_delete=models.CASCADE,
        related_name="period_confirmations",
        verbose_name="الشعبة",
    )
    date = models.DateField(db_index=True, verbose_name="التاريخ")
    start_time = models.TimeField(verbose_name="بدءُ الخانة")
    end_time = models.TimeField(verbose_name="نهايةُ الخانة")
    confirmed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="period_confirmations",
        verbose_name="أكّده",
    )
    first_confirmed_at = models.DateTimeField(verbose_name="أوّلُ تثبيت")
    confirmed_at = models.DateTimeField(auto_now=True, verbose_name="آخرُ تثبيت")
    confirmed_late = models.BooleanField(default=False, verbose_name="ثُبّتت بعد مهلتها")
    present_count = models.PositiveSmallIntegerField(default=0, verbose_name="الحاضرون")
    absent_count = models.PositiveSmallIntegerField(default=0, verbose_name="الغائبون")
    late_count = models.PositiveSmallIntegerField(default=0, verbose_name="المتأخّرون")

    class Meta:
        verbose_name = "تثبيتُ رصدِ حصّة"
        verbose_name_plural = "تثبيتاتُ رصد الحصص"
        ordering = ["-date", "class_group", "start_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["class_group", "date", "start_time"],
                name="unique_period_confirmation",
            )
        ]
        indexes = [models.Index(fields=["school", "date"])]

    def __str__(self):
        return f"{self.class_group.short_code} · {self.date} {self.start_time:%H:%M}"
