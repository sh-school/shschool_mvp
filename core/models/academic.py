from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateRangeField, RangeBoundary, RangeOperators
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Func, Q
from django.db.models.functions import Cast, Substr
from django.utils import timezone

from core.academic_calendar import default_academic_year

from .school import School, _uuid
from .user import CustomUser


class AcademicYear(models.Model):
    """
    العام الدراسي — يُستخدم لتحديد السنة الأكاديمية النشطة لكل مدرسة.

    UniqueConstraint يمنع وجود أكثر من عام دراسي حالي لنفس المدرسة.
    """

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="academic_years",
        verbose_name="المدرسة",
    )
    name = models.CharField(
        max_length=9,
        verbose_name="العام الدراسي",
        help_text="مثال: 2025-2026",
    )
    start_date = models.DateField(verbose_name="تاريخ البداية")
    end_date = models.DateField(verbose_name="تاريخ النهاية")
    is_current = models.BooleanField(default=False, verbose_name="العام الحالي")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "عام دراسي"
        verbose_name_plural = "الأعوام الدراسية"
        ordering = ["-start_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "name"],
                name="unique_academic_year_per_school",
            ),
            models.UniqueConstraint(
                fields=["school"],
                condition=models.Q(is_current=True),
                name="unique_current_academic_year_per_school",
            ),
        ]

    def __str__(self):
        current = " ✓" if self.is_current else ""
        return f"{self.name}{current} — {self.school.name}"


#: ترتيبُ الصفّ عدداً لا حرفاً.
#:
#: `grade` نصٌّ («G7» … «G12»)، وترتيبُه الأبجديُّ يضع العاشرَ والحادي عشر
#: والثاني عشر **قبل** السابع — فتخرج قوائمُ الشُّعب في الشاشات هكذا:
#:
#:     10/1 … 10/4 · 11/1 … 11/4 · 12/1 … 12/4 · 7/1 …
#:
#: وهو ترتيبٌ لا يقرؤه أحدٌ في مدرسة. فيُقتطع الحرفُ الأوّل ويُقرأ ما بعده
#: عدداً: 7 ثمّ 8 … ثمّ 12.
def grade_order(field: str = "grade"):
    """ترتيبٌ تصاعديٌّ بالصفّ عبر أيّ مسار علاقة.

        .order_by(grade_order("class_group__grade"), "class_group__section")

    ولا يصلح لاستعلامٍ يجمع `values_list(...).distinct()`: الترتيبُ بتعبيرٍ
    خارج قائمة الاختيار يرفضه المحرّك — فتلك تُفرَز بـ`grade_number` في
    بايثون.
    """
    return Cast(Substr(field, 2), models.IntegerField()).asc()


GRADE_ORDER = Cast(Substr("grade", 2), models.IntegerField())


def grade_number(grade: str) -> int:
    """رقمُ الصفّ من رمزه: «G12» → 12. وما لا يُقرأ يذهب إلى الذيل.

    لفرزٍ في بايثون حيث يتعذّر في القاعدة — كقوائم الصفوف المميَّزة
    (`distinct`)، فالترتيبُ بتعبيرٍ خارج قائمة الاختيار يرفضه المحرّك.
    """
    digits = (grade or "").removeprefix("G")
    return int(digits) if digits.isdigit() else 99


class ClassGroupQuerySet(models.QuerySet):
    def in_school_order(self):
        """من 7/1 إلى 12/4 — ترتيبُ المدرسة لا ترتيبُ الحروف."""
        return self.order_by(GRADE_ORDER.asc(), "section")


class ClassGroupManager(models.Manager.from_queryset(ClassGroupQuerySet)):
    """الترتيبُ المدرسيُّ افتراضٌ لا استثناء — فمن نسي `order_by` أصاب.

    و`Meta.ordering` لا يسعه: ترتيبُنا تعبيرٌ محسوبٌ لا اسمُ حقل، ووضعُه هناك
    يمرّ على مُسلسِل الهجرات.
    """

    def get_queryset(self):
        return super().get_queryset().order_by(GRADE_ORDER.asc(), "section")


#: طوابقُ المبنى — يقرؤه الجرسُ (`TimeBand.floor`) والجناحُ (`Wing.floor`) معاً.
#:
#: وُضع في موضعٍ واحدٍ لأنّ الطابقَ ليس صفةً في اثنين: هو **الرابطُ** بينهما.
#: فجناحٌ في الأرضيّ لا تصحّ فيه شعبةٌ على جرسٍ علويّ، ومن كتب القائمةَ مرّتين
#: أمكنه أن يزيد قيمةً في إحداهما فيصير الفحصُ بلا معنى.
FLOORS = [("ground", "الطابق الأرضيّ"), ("first", "الطابق الأوّل")]


class TimeBand(models.Model):
    """نطاقُ توقيت: مجموعةُ شُعبٍ تتقاسم جرسَ اليوم نفسَه.

    المدرسةُ طابقان، وأجراسُها **ثلاثة** لا اثنان — وهذا ما يجعل «الطابق» لا
    يكفي وحدَه مفتاحاً للتوقيت:

        الأرضيّ   ground     السابع · الثامن · تاسع/1 · تاسع/2
        الأوّل    ninth      تاسع 3 · تاسع 4
        الأوّل    secondary  العاشر إلى الثاني عشر

    فمن الأحد إلى الأربعاء يتطابق جرسا الطابق الأوّل حرفاً، ويوم **الخميس
    يفترقان**: تاسع 3·4 فسحتُهم بعد الثالثة وصلاتُهم آخرَ اليوم، والثانويُّ
    فسحتُه بعد الرابعة وحصصُه أقصر. فثلاثةُ أجراسٍ يومَ الخميس واثنان قبله.

    والطابقُ محفوظٌ هنا لا مشتقٌّ من الرمز: بلا حقلٍ لا يعرف الخلفيّةُ أنّ
    `ninth` و`secondary` طابقٌ واحد، فيتعذّر السؤالُ «ما يرنّه الطابقُ الأوّلُ
    الآن؟» إلّا بتسميةِ رموزٍ في الكود — وهي تسميةٌ تكذب في أوّل جرسٍ يُضاف.

    والنسبةُ بالشعبة لا بالمرحلة: تاسع/1 وتاسع/2 أرضيّان، وتاسع 3·4 علويّان
    (نُقل تاسع/2 إلى الأرضيّ بقرار الإدارة 2026-09-09).
    """

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="time_bands")
    code = models.SlugField(max_length=20, verbose_name="الرمز")
    name = models.CharField(max_length=60, verbose_name="الاسم")
    #: طابقُ الجرس — ولا يُشتقّ من الرمز. راجع صدرَ الصنف.
    floor = models.CharField(max_length=6, choices=FLOORS, default="ground", verbose_name="الطابق")
    order = models.PositiveSmallIntegerField(default=0, verbose_name="الترتيب")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "نطاق توقيت"
        verbose_name_plural = "نطاقات التوقيت"
        ordering = ["order", "code"]
        constraints = [
            models.UniqueConstraint(fields=["school", "code"], name="unique_time_band_per_school")
        ]

    def __str__(self):
        return self.name


#: أجراسُ مجموعةٍ من الشُّعب مرتّبةً بلا تكرار.
#:
#: دالّةٌ لا خاصّيّةٌ لأنّ لها نداءين: `Wing.time_bands` يمرّر استعلامَه،
#: وشاشةُ الأجنحة تمرّر ما سبق جلبُه بـ`prefetch_related` — فلو كُتب المنطقُ
#: في الخاصّيّة وحدَها لأعادت الشاشةُ الاستعلامَ خمسَ مرّاتٍ أو كرّرت المنطق.
def bands_of(sections) -> list:
    bands = {klass.time_band for klass in sections if klass.time_band_id}
    return sorted(bands, key=lambda band: (band.order, band.code))


class Wing(models.Model):
    """جناحٌ من أجنحة المدرسة الخمسة: ممرٌّ بخمس شُعبٍ ومشرفٍ إداريٍّ واحد.

    المدرسةُ خمسةُ أجنحة، لكلٍّ مشرفٌ إداريّ، وخمسُ شُعبٍ لكلّ جناحٍ بلا تكرارٍ
    ولا فراغ — خمسٌ وعشرون شعبةً (قرار الإدارة 2026-09-09). وشُعبُ التربية
    الخاصّة الثلاث **خارجَ الأجنحة** بقرارٍ صريح: حضورُها بيد معلّميها، فتبقى
    `ClassGroup.wing` فيها فارغةً عمداً لا سهواً.

    والجناحُ ليس زينةً في شاشة: هو **نطاقُ** مشرفه — من يقرأ ومن يكتب ومن
    يعتمد العذرَ ومن يصله صندوقُ المخالفات. فكلُّ صلاحيّةٍ في المرحلة 3 تمرّ
    عليه.

    وثلاثُ خصائصَ تجعل الحدّ الأعلى للتعميم منخفضاً، ولذلك تُحسب لا تُفترض:

    1. **الجناحُ قد يعبر جرسين.** جناح 3 فيه 9/3 و9/4 على جرس التاسع و10/1–3
       على جرس الثانويّ — فـ«الحصّةُ الحالية» فيه لا تُقال برقمٍ بل بالساعة.
       `is_split_band` يقول ذلك، ولا يُقرأ رقمُ الحصّة من الشعبة الأولى.
    2. **الجناحُ قد يعبر مرحلتين.** جناح 3 تاسعٌ إعداديٌّ وعاشرٌ ثانويّ —
       سياستان في ممرٍّ واحد، فـ`levels` مجموعةٌ لا قيمة.
    3. **الجناحُ قد يكون صفّاً واحداً تقريباً.** أربعُ شُعبِ جناح 5 ثاني عشر،
       وعتباتُ غيابه تخالف عتبات ما دونه — فعرضُ العتبة العامّة يكذب في
       أغلب طلابه.

    والصفُّ الواحدُ في عامين جناحان: الصفوفُ تتحرّك والمشرفون يتبدّلون، فحمل
    السجلُّ `academic_year` وصار سجلَّ عامٍ لا سجلَّ مبنى.
    """

    #: قائمةٌ واحدةٌ يقرؤها الجرسُ والجناح — راجع `FLOORS` في صدر الملفّ.
    FLOORS = FLOORS

    #: من يصلح مشرفاً لجناح. والنائبُ الإداريُّ منهم لأنّه يرث المشرف
    #: (`core/permissions.py`) — فيصحّ أن يحمل جناحاً عند النقص.
    SUPERVISOR_ROLES = ("admin_supervisor", "vice_admin")

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="wings")
    code = models.SlugField(max_length=20, verbose_name="الرمز")
    name = models.CharField(max_length=60, verbose_name="الاسم")
    floor = models.CharField(max_length=6, choices=FLOORS, default="ground", verbose_name="الطابق")
    order = models.PositiveSmallIntegerField(default=0, verbose_name="الترتيب")
    #: يبقى فارغاً حتّى تسمّي الإدارةُ المشرفين — وجناحٌ بلا مشرفٍ حالةٌ
    #: تُعرض وتُنبَّه، لا حالةٌ يُمنع حفظُها.
    supervisor = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supervised_wings",
        verbose_name="المشرف الإداريّ",
    )
    academic_year = models.CharField(max_length=9, default=default_academic_year)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "جناح"
        verbose_name_plural = "الأجنحة"
        ordering = ["order", "code"]
        constraints = [
            # الرمزُ مع العام لا الرمزُ وحدَه: «جناح 1» يتكرّر كلَّ عامٍ بشُعبٍ
            # ومشرفٍ غيرِ ما كان، فقيدٌ بلا عامٍ يمنع فتحَ العام القادم.
            models.UniqueConstraint(
                fields=["school", "code", "academic_year"],
                name="unique_wing_code_per_year",
            ),
            # ولا يحمل أحدٌ جناحين في عامٍ واحد: خمسةُ أجنحةٍ لخمسةِ أشخاص،
            # ومن حمل اثنين صار نقطةَ فشلٍ مضاعفة. والقيدُ جزئيٌّ كي لا
            # يتصادم جناحان بلا مشرفٍ بعدُ (`NULL` لا يساوي `NULL` في
            # الفهرس، لكنّ الشرطَ يقولها صراحةً لقارئ الهجرة).
            models.UniqueConstraint(
                fields=["school", "supervisor", "academic_year"],
                condition=models.Q(supervisor__isnull=False, is_active=True),
                name="unique_wing_supervisor_per_year",
            ),
        ]

    def clean(self):
        """مشرفُ الجناح عضوٌ نشطٌ بدورٍ يسمح — لا أيُّ مستخدمٍ في القاعدة."""
        super().clean()
        if self.supervisor_id is None or self.school_id is None:
            return
        from .access import Membership

        eligible = Membership.objects.filter(
            user_id=self.supervisor_id,
            school_id=self.school_id,
            is_active=True,
            role__name__in=self.SUPERVISOR_ROLES,
        ).exists()
        if not eligible:
            raise ValidationError(
                {"supervisor": "مشرفُ الجناح عضوٌ نشطٌ بدور «مشرف إداريّ» أو «النائب الإداريّ»."}
            )

    @property
    def sections(self):
        """شُعبُ الجناح النشطةُ بترتيب المدرسة."""
        return self.class_groups.filter(is_active=True)

    @property
    def student_count(self) -> int:
        return StudentEnrollment.objects.filter(class_group__wing=self, is_active=True).count()

    @property
    def time_bands(self) -> list:
        """أجراسُ الجناح — واحدٌ في الغالب، واثنان في جناحٍ يعبر طابقين.

        باستعلامٍ واحد: كانت قراءةُ المعرّفات ثمّ قراءةُ الأجراس استعلامَين،
        وخمسةُ أجنحةٍ تُعرض معاً تجعلهما عشرة.
        """
        return bands_of(self.class_groups.filter(is_active=True).select_related("time_band"))

    @property
    def is_split_band(self) -> bool:
        """جناحٌ بجرسين لا يُقال فيه «الحصّة الثالثة» — تُقال الساعة."""
        return len(self.time_bands) > 1

    @property
    def bells_off_floor(self) -> list:
        """أجراسُ الجناح التي طابقُها ليس طابقَه — والصحيحُ أن تكون فارغة.

        شعبةٌ في جناحٍ أرضيٍّ على جرسٍ علويٍّ تعني أنّ أحدَ الرقمين خطأ: إمّا
        نسبةُ الشعبة إلى جناحها وإمّا نسبتُها إلى جرسها. وأثرُه لا يُرى في
        شاشةِ أجنحة: يُرى معلّماً يدخل فصلاً بعد أن خرج طلابُه، وطالباً
        يُرصد غائباً في حصّةٍ لم تبدأ عنده بعد.

        ولا يُفرَض في القاعدة: القيدُ يعبر ثلاثةَ جداول (جناح ← شعبة ← جرس)
        فلا يبلغه `CHECK`. فيُقاس ويُعرض — و`seed_wings` يقوله في تقريره.
        """
        return [band for band in self.time_bands if band.floor != self.floor]

    @property
    def levels(self) -> set:
        """مراحلُ الجناح — مجموعةٌ لأنّ جناحاً واحداً يعبر الإعداديَّ والثانويّ."""
        return set(self.class_groups.filter(is_active=True).values_list("level_type", flat=True))

    def active_coverage(self, on_date=None):
        """التغطيةُ الساريةُ في هذا اليوم — أو `None`.

        والأحدثُ بدايةً يغلب عند التساوي: قيدُ الاستبعاد يمنع التداخلَ في
        القاعدة، لكنّ قراءةً بلا ترتيبٍ تُرجع ما تُرجعه القاعدةُ أوّلاً.
        """
        day = on_date or timezone.localdate()
        return (
            self.coverages.filter(start_date__lte=day)
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=day))
            .select_related("substitute")
            .order_by("-start_date")
            .first()
        )

    def current_supervisor(self, on_date=None):
        """من يحمل الجناحَ في هذا اليوم — البديلُ إن غُطّي، وإلّا الأصيل.

        **كلُّ صلاحيّةٍ واستعلامٍ يمرّ على هذه**، لا على `supervisor`. فالأصيلُ
        حقيقةُ سجلٍّ والحاملُ حقيقةُ يوم: مشرفٌ في إجازةٍ أسبوعاً يبقى أصيلَ
        جناحه، ومن يقرأ ملفّات طلابه في ذلك الأسبوع غيرُه. ومن قرأ `supervisor`
        مباشرةً منح الغائبَ ومنع الحاضر.
        """
        cover = self.active_coverage(on_date)
        return cover.substitute if cover else self.supervisor

    def __str__(self):
        return f"{self.name} ({self.academic_year})"


class DateRange(Func):
    """`daterange(بداية، نهاية، '[]')` — ونهايةٌ فارغةٌ تعني مدّةً بلا أفق."""

    function = "DATERANGE"
    output_field = DateRangeField()


class WingCoverage(models.Model):
    """تغطيةُ جناحٍ في غياب مشرفه — مدّةٌ لا علمٌ يُرفع ويُنزل.

    الجناحُ نطاقُ مشرفه، فغيابُه يوماً يعني خمسَ شُعبٍ لا يرصد غيابَها أحد،
    وعذراً لا يعتمده أحد، وصندوقَ مخالفاتٍ لا يفتحه أحد. ولهذا لا يكفي حقلٌ
    بوليٌّ «غائب»: يلزم **من** يحمله و**إلى متى**.

    ولهذا هو سجلٌّ زمنيٌّ لا حقلٌ على الجناح: الحقلُ يُكتب فوق سابقه فلا يبقى
    أثرٌ لمن حمل الجناحَ في يومٍ ماضٍ — ومن يقرأ غيابَ الأسبوع الماضي يحتاج أن
    يعرف من كان يرصده. والسجلُّ يُقرأ بالتاريخ، فيُجيب عن أمسِ كما يُجيب عن
    اليوم.

    ## من يصلح بديلاً

    قرارُ المدير 2026-09-12: «جميعُ من مسمّاه مشرفٌ إداريٌّ، عاملُ خدمات،
    وملاحظُ حافلة» — وملاحظُ الحافلة هو ملاحظُ الطلبة نفسُه.

    ويُقرأ الحوضُ **بالدور** لا بنصّ المسمّى الوظيفيّ: المسمّى نصٌّ حرٌّ يُكتب
    «ملاحظ طلبه» بهاءٍ في كشفٍ و«ملاحظ طلبة» بتاءٍ في آخر، ومطابقةُ نصٍّ حرٍّ
    لا تصلح صلاحيّة. و**مشرفُ المقصف** يحمل لفظَ «مشرف» وليس من الحوض —
    فمطابقةُ الكلمة كانت ستضمّه.

    ## ولا تتداخل مدّتان

    قيدُ استبعادٍ في القاعدة على (الجناح، المدّة): تغطيتان متداخلتان لجناحٍ
    واحدٍ تعنيان أنّ اثنين يحملانه في يومٍ واحد، فيقرأ كلاهما ويكتب كلاهما
    ولا يُدرى من المسؤول. و`clean()` وحدَه لا يكفي: كتابتان متزامنتان تمرّان
    عليه معاً ثمّ تقعان معاً.
    """

    REASONS = [
        ("absence", "غيابُ المشرف"),
        ("leave", "إجازة"),
        ("vacancy", "جناحٌ بلا مشرف"),
        ("other", "أخرى"),
    ]

    #: من يصلح بديلاً — بالدور، مقابلاً لمسمّيات المدير الثلاثة.
    SUBSTITUTE_ROLES = ("admin_supervisor", "services_worker", "student_observer")

    #: من يعيّن. والأكاديميُّ منهم لأنّه يحمل صلاحيّاتِ المدير في غيابه عادةً —
    #: وحصرُه في الإداريّ يعني جناحاً بلا مشرفٍ يومَ يغيب المديرُ ونائبُه معاً.
    ASSIGNER_ROLES = ("principal", "vice_admin", "vice_academic", "platform_developer")

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    wing = models.ForeignKey("core.Wing", on_delete=models.CASCADE, related_name="coverages")
    substitute = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name="wing_coverages",
        verbose_name="البديل",
    )
    assigned_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wing_coverages_assigned",
        verbose_name="عيّنه",
    )
    reason = models.CharField(max_length=10, choices=REASONS, default="absence")
    start_date = models.DateField(verbose_name="من")
    #: فارغةٌ = مفتوحةٌ حتّى تُنهى. ومدّةٌ بلا نهايةٍ ليست إهمالاً: غيابٌ طارئٌ
    #: لا يُعرف مداه يومَ يقع، والتاريخُ يُكتب حين يعود صاحبُه.
    end_date = models.DateField(null=True, blank=True, verbose_name="إلى")
    ended_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wing_coverages_ended",
        verbose_name="أنهاها",
    )
    note = models.TextField(blank=True, verbose_name="ملاحظة")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "تغطيةُ جناح"
        verbose_name_plural = "تغطياتُ الأجنحة"
        ordering = ["-start_date"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=models.F("start_date")),
                name="wing_coverage_ends_after_it_starts",
            ),
            ExclusionConstraint(
                name="no_overlapping_wing_coverage",
                expressions=[
                    (
                        DateRange("start_date", "end_date", RangeBoundary(inclusive_upper=True)),
                        RangeOperators.OVERLAPS,
                    ),
                    ("wing", RangeOperators.EQUAL),
                ],
            ),
        ]
        indexes = [models.Index(fields=["wing", "start_date"])]

    def covers(self, day) -> bool:
        return self.start_date <= day and (self.end_date is None or day <= self.end_date)

    def clean(self):
        """أربعةُ شروطٍ يبلغها المُدخِلُ في حقله، لا رفضاً من المحرّك بلا بيان."""
        super().clean()
        errors = {}

        if self.end_date and self.start_date and self.end_date < self.start_date:
            errors["end_date"] = "النهايةُ قبل البداية."

        if self.substitute_id and self.wing_id:
            if self.substitute_id == self.wing.supervisor_id:
                errors["substitute"] = "البديلُ هو الأصيلُ نفسُه — لا تغطيةَ في ذلك."
            else:
                from .access import Membership

                eligible = Membership.objects.filter(
                    user_id=self.substitute_id,
                    school_id=self.wing.school_id,
                    is_active=True,
                    role__name__in=self.SUBSTITUTE_ROLES,
                ).exists()
                if not eligible:
                    errors["substitute"] = "البديلُ من مشرفٍ إداريٍّ أو عاملِ خدماتٍ أو ملاحظِ طلبة."

        # ولا يحمل أحدٌ تغطيتين متداخلتين: نقطةُ فشلٍ مضاعفةٌ في يومٍ واحد.
        if self.substitute_id and self.start_date:
            clash = (
                WingCoverage.objects.filter(substitute_id=self.substitute_id)
                .exclude(pk=self.pk)
                .filter(Q(end_date__isnull=True) | Q(end_date__gte=self.start_date))
            )
            if self.end_date:
                clash = clash.filter(start_date__lte=self.end_date)
            other = clash.select_related("wing").first()
            if other:
                errors["substitute"] = (
                    f"يغطّي {other.wing.name} في المدّة نفسها — ولا تغطيتين لشخصٍ واحد."
                )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        end = f"{self.end_date}" if self.end_date else "مفتوحة"
        return f"{self.wing.name}: {self.substitute.full_name} ({self.start_date} → {end})"


class ClassGroup(models.Model):
    GRADES = [
        ("G7", "الصف السابع"),
        ("G8", "الصف الثامن"),
        ("G9", "الصف التاسع"),
        ("G10", "الصف العاشر"),
        ("G11", "الصف الحادي عشر"),
        ("G12", "الصف الثاني عشر"),
    ]
    LEVELS = [("prep", "إعدادي"), ("sec", "ثانوي")]

    #: مسارات المرحلة الثانوية. يختارها الطالب بعد نجاحه في العاشر، فتبدأ من
    #: الحادي عشر وتشمل الثاني عشر.
    #:
    #: والمدرسة مدمجة: ٧–٩ إعدادي، و١٠–١٢ ثانوي. **والعاشر ثانويٌّ بلا مسار** —
    #: وهو ما يجعل `level_type == "sec"` قيداً غير كافٍ، لأن العاشر يجتازه.
    TRACKS = [
        ("science", "علمي"),
        ("humanities", "آداب وإنسانيات"),
        ("technology", "تكنولوجي"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="class_groups")
    grade = models.CharField(max_length=3, choices=GRADES)
    section = models.CharField(max_length=10, verbose_name="الشعبة")
    level_type = models.CharField(max_length=4, choices=LEVELS, default="prep")
    #: جرسُ الشعبة — فارغٌ يعني «جرسَ المدرسة الافتراضيّ». راجع `TimeBand`.
    time_band = models.ForeignKey(
        "core.TimeBand",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="class_groups",
        verbose_name="نطاق التوقيت",
    )
    #: فارغٌ في الإعدادي وفي العاشر. وشعبةُ الحادي عشر أو الثاني عشر بلا مسار
    #: حالةٌ مشروعة حتى يُحدَّد — فلا يُجبَر المُدخِل على اختيارٍ لم يُتّخذ بعد.
    #:
    #: ولا يُقيَّد بالصفّ في قاعدة البيانات: القيد في `clean()` كي يبلغ الخطأُ
    #: الحقلَ نفسه في الاستمارة، بدل رفضٍ من المحرّك بلا بيان.
    track = models.CharField(max_length=12, choices=TRACKS, blank=True, verbose_name="المسار")
    academic_year = models.CharField(max_length=9, default=default_academic_year)
    #: جناحُ الشعبة — وفارغُه ليس نقصاً دائماً: شُعبُ التربية الخاصّة خارجَ
    #: الأجنحة بقرار الإدارة. و`seed_wings` يسمّي كلَّ شعبةٍ بلا جناحٍ كي لا
    #: يُقرأ الفارغُ المقصودُ والفارغُ المنسيُّ سواءً.
    wing = models.ForeignKey(
        "core.Wing",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="class_groups",
        verbose_name="الجناح",
    )
    #: مهجورٌ منذ 2026-09-12 لصالح `wing.supervisor`: كان حقلاً شبهَ ميّتٍ
    #: يُعرض اسمُه في شاشةٍ واحدة ولا يُستعلَم عنه، والإشرافُ صار على الجناح
    #: لا على الشعبة. يُحذف بعد نقل استخدامه الأخير.
    supervisor = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supervised_classes",
    )
    is_active = models.BooleanField(default=True)

    #: شعبةٌ جدولُها خارج هذا النظام — تُستثنى من الخطّة الدراسيّة والإسناد
    #: والتغطية والمولّد.
    #:
    #: وشُعبُ التربية الخاصّة (8/ESE و9/ESE و10/ESE) كذلك بقرار الإدارة: لها
    #: جدولٌ خاصٌّ لا يتبع جدولَ المدرسة، ودليلُ الوزارة يفرد لها خططاً
    #: مستقلّة. وكانت تظهر قبل هذا العلم «شعبةً بلا إسناد» في كلّ فحصِ
    #: تغطيةٍ إلى الأبد — والاستثناءُ المقصودُ يُكتب، ولا يُترك تجاهلاً صامتاً
    #: يظنّه القارئُ بعد سنةٍ خللاً في البيانات.
    has_own_timetable = models.BooleanField(
        default=False,
        verbose_name="جدولٌ مستقلّ",
        help_text="شعبةٌ خارج الجدول العامّ — لا خطّةَ لها ولا إسنادَ ولا توليد",
    )

    objects = ClassGroupManager()

    class Meta:
        # «الفصل الدراسي» مصطلحُ الوزارة للمدّة الزمنية (الأول/الثاني)، وهو
        # اسم `Semester`. وهذا النموذج يحمل `grade` و`section` معاً — أي
        # الشعبة داخل الصف — فكانت التسميتان متطابقتين في لوحة الإدارة
        # وتقودان إلى شيئين لا صلة بينهما.
        verbose_name = "شعبة دراسية"
        verbose_name_plural = "الشُّعب الدراسية"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "grade", "section", "academic_year"],
                name="unique_class_per_year",
            )
        ]
        indexes = [models.Index(fields=["school", "grade", "academic_year"])]

    #: الصفوف التي تحمل مساراً — والعاشر ليس منها وإن كان ثانوياً.
    TRACKED_GRADES = ("G11", "G12")

    def clean(self):
        """المسار للحادي عشر والثاني عشر — ومن أخطأ يُخبَر لا يُرفض بلا بيان."""
        super().clean()
        if self.track and self.grade not in self.TRACKED_GRADES:
            raise ValidationError({"track": "المسار للصفّين الحادي عشر والثاني عشر وحدهما."})

    @property
    def short_code(self):
        """رمز الشعبة المختصر كما في الجدول العام: «12.4» و«7.ESE».

        الصفُّ رقمٌ لا رمزٌ في ورقة الجدول — سبعٌ وثمانٍ لا `G7` و`G8` —
        والشعبةُ عددُها وحده. وشعبُ التربية الخاصة تحمل بادئةَ صفٍّ في
        `section` نفسه («07/ESE»)، فتكرارُها بعد رقم الصفّ حشوٌ يضيّق
        خانةً عرضُها حرفان.
        """
        grade = self.grade.removeprefix("G")
        section = self.section.rsplit("/", 1)[-1]
        return f"{grade}.{section}"

    @property
    def school_order(self) -> int:
        """مفتاحُ الترتيب المدرسيّ عدداً: 7/1 → 701 و12/4 → 1204.

        الشاشاتُ تعرض «الصف السابع / 1» نصّاً، وفرزُ ذلك النصِّ يضع العاشرَ
        قبل السابع. فيُعطى العمودُ مفتاحاً عدديّاً يُفرَز به بدل حروفه.
        وشعبةُ التربية الخاصّة لا عددَ لها فتُلحق بذيل صفِّها لا بذيل المدرسة.
        """
        section = self.section.rsplit("/", 1)[-1]
        return grade_number(self.grade) * 100 + (int(section) if section.isdigit() else 99)

    def __str__(self):
        track = f" — {self.get_track_display()}" if self.track else ""
        return f"{self.get_grade_display()} / {self.section}{track} ({self.academic_year})"


class StudentEnrollmentQuerySet(models.QuerySet):
    """قيدُ الطالب مدّةٌ لا حالة — و`is_active` وحدَها لا تقول في أيّ عام.

    القيدُ القديم لا يُغلق عند بداية العام: المستورِد يُطفئ القيدَ حين ينتقل
    الطالبُ داخل العام نفسِه، أمّا قيدُ العام الماضي فخارجُ نظره. والقيدُ
    الفريدُ في القاعدة مفروضٌ على الزوج (طالب، شعبة) — وهما شعبتان في عامين
    فيمرّ. فحمل مئاتُ الطلاب قيدَين نشطَين معاً.

    و`filter(student=…, is_active=True).first()` بلا ترتيبٍ يُرجع ما تُرجعه
    القاعدةُ أوّلاً — أي صفّاً عشوائيّاً. قِيس ذلك على بيانات المدرسة: من 448
    طالباً بقيدَين، 215 كانوا يُعرضون في صفِّ العام الماضي. وأسوأُ من الخطأ
    أنّه غيرُ ثابت: ترتيبُ الصفوف يتغيّر بعد أيّ تحديثٍ أو كنس، فيصحّ الطالبُ
    اليومَ ويُخطئ غداً بلا تغييرٍ في البيانات.
    """

    def newest_first(self) -> "StudentEnrollmentQuerySet":
        """الأحدثُ عاماً أوّلاً — واسمُ العام «2026-2027» يُفرَز نصّاً كما يُقرأ."""
        return self.order_by("-class_group__academic_year", "-enrolled_at")


class StudentEnrollmentManager(models.Manager.from_queryset(StudentEnrollmentQuerySet)):
    """السؤالُ «في أيّ شعبةٍ هذا الطالب؟» يمرّ من هنا وحدَه."""

    def current_of(self, student, school=None):
        """قيدُ الطالب القائم — أحدثُ قيودِه النشطة عاماً، أو `None`.

        ولا يُقيَّد بالعام الجاري قصداً: طالبٌ لم يُقيَّد بعدُ لهذا العام يبقى
        له صفٌّ يُعرض به بدل أن تخلو شاشتُه — والأحدثُ حتماً أصوبُ من العشوائيّ.
        """
        qs = self.filter(student=student, is_active=True)
        if school is not None:
            qs = qs.filter(class_group__school=school)
        return qs.select_related("class_group").newest_first().first()


class StudentEnrollment(models.Model):
    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="enrollments")
    class_group = models.ForeignKey(
        ClassGroup, on_delete=models.CASCADE, related_name="enrollments"
    )
    is_active = models.BooleanField(default=True)
    enrolled_at = models.DateField(default=timezone.now)

    objects = StudentEnrollmentManager()

    class Meta:
        verbose_name = "تسجيل طالب"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "class_group"],
                condition=models.Q(is_active=True),
                name="unique_active_enrollment",
            )
        ]
        indexes = [
            models.Index(fields=["class_group", "is_active"], name="idx_enrollment_class_active"),
            models.Index(fields=["student", "is_active"], name="idx_enrollment_student_active"),
        ]

    def __str__(self):
        return f"{self.student.full_name} → {self.class_group}"


class ParentStudentLink(models.Model):
    RELATIONSHIP = [
        ("father", "الأب"),
        ("mother", "الأم"),
        ("guardian", "الوصي"),
        ("other", "أخرى"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="parent_links")
    parent = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="children_links",
        verbose_name="ولي الأمر",
    )
    student = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="parent_links",
        verbose_name="الطالب",
    )
    relationship = models.CharField(
        max_length=20, choices=RELATIONSHIP, default="father", verbose_name="صلة القرابة"
    )
    is_primary = models.BooleanField(default=True, verbose_name="ولي الأمر الأساسي")
    can_view_grades = models.BooleanField(default=True, verbose_name="يرى الدرجات")
    can_view_attendance = models.BooleanField(default=True, verbose_name="يرى الغياب")
    can_view_behavior = models.BooleanField(default=True, verbose_name="يرى السلوك")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "ربط ولي أمر"
        verbose_name_plural = "ربط أولياء الأمور"
        ordering = ["student__full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "student", "school"],
                name="unique_parent_student_school",
            )
        ]

    def __str__(self):
        return (
            f"{self.parent.full_name} ← {self.student.full_name} "
            f"({self.get_relationship_display()})"
        )


class Semester(models.Model):
    """الفصل الدراسي — حدودُه تواريخُ تقويم الوزارة، لا رايةٌ يُبدّلها أحد.

    «الفصل الحالي» يُشتقّ من التاريخ (`AcademicCalendar.current`)، فلا يوجد
    `is_current` هنا عمداً: رايةٌ كهذه تُنسى، فتُسجَّل درجاتٌ في الفصل الخطأ
    ولا شيء يكشف ذلك.

    والفصلان متلاصقان بلا فجوة — إجازة منتصف العام تُلحق بالفصل المنتهي —
    كي لا يأتي يومٌ بلا فصلٍ فتضطرّ كل شاشة إلى اختراع سلوكٍ لتلك الحالة.
    """

    CODES = [
        ("S1", "الفصل الدراسي الأول"),
        ("S2", "الفصل الدراسي الثاني"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="semesters",
        verbose_name="العام الدراسي",
    )
    code = models.CharField(max_length=2, choices=CODES, verbose_name="الفصل")
    start_date = models.DateField(verbose_name="تاريخ البداية")
    end_date = models.DateField(verbose_name="تاريخ النهاية")
    max_grade = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name="الدرجة القصوى",
        help_text="٤٠ للفصل الأول و٦٠ للثاني — وزن الفصل بياناتٌ لا ثابتٌ في الشيفرة",
    )

    class Meta:
        verbose_name = "فصل دراسي"
        verbose_name_plural = "الفصول الدراسية"
        ordering = ["academic_year", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["academic_year", "code"],
                name="unique_semester_code_per_year",
            ),
            models.CheckConstraint(
                condition=models.Q(end_date__gt=models.F("start_date")),
                name="semester_ends_after_it_starts",
            ),
        ]

    def __str__(self):
        return f"{self.get_code_display()} — {self.academic_year.name}"

    def covers(self, day):
        return self.start_date <= day <= self.end_date


class CalendarEvent(models.Model):
    """حدثٌ في تقويم الوزارة — اختبارٌ أو إجازةٌ أو بدء دوام.

    ثلاثة حقول تفصله عن «تاريخٍ ونصّ»، وكلٌّ منها فرضه التقويم نفسه:

      `grade_scope`   نوافذ الاختبارات تختلف: الصفوف ١–٩ · ١٠–١١ · ١٢
      `audience`      الموظفون يبدأون قبل الطلبة بأسبوع
      `academic_year` اختبارات الدور الثاني لعامٍ تقع في تقويم العام التالي،
                      فالحدث ينتمي إلى عامٍ قد لا يكون عام تاريخه
    """

    TYPES = [
        ("staff_start", "بدء دوام الموظفين"),
        ("students_start", "بدء دوام الطلبة"),
        ("midterm_exam", "اختبارات منتصف الفصل"),
        ("final_exam", "اختبارات نهاية الفصل"),
        ("makeup_exam", "ملحق الاختبارات"),
        ("second_round", "اختبارات الدور الثاني"),
        ("break", "إجازة"),
        ("resume", "استئناف الدوام"),
    ]

    GRADE_SCOPES = [
        ("all", "جميع الصفوف"),
        ("g1_9", "الصفوف ١–٩"),
        ("g10_11", "الصفّان ١٠–١١"),
        ("g12", "الصف ١٢"),
    ]

    AUDIENCES = [
        ("both", "الجميع"),
        ("staff", "الموظفون"),
        ("students", "الطلبة"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="calendar_events",
        verbose_name="العام الدراسي",
    )
    semester = models.ForeignKey(
        Semester,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="calendar_events",
        verbose_name="الفصل",
    )
    event_type = models.CharField(max_length=20, choices=TYPES, verbose_name="النوع")
    name = models.CharField(max_length=200, verbose_name="البيان")
    start_date = models.DateField(verbose_name="من")
    end_date = models.DateField(verbose_name="إلى")
    grade_scope = models.CharField(
        max_length=10, choices=GRADE_SCOPES, default="all", verbose_name="نطاق الصفوف"
    )
    audience = models.CharField(
        max_length=10, choices=AUDIENCES, default="both", verbose_name="الجمهور"
    )

    class Meta:
        verbose_name = "حدث تقويم"
        verbose_name_plural = "أحداث التقويم"
        ordering = ["start_date", "event_type"]
        indexes = [models.Index(fields=["academic_year", "start_date"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="calendar_event_ends_after_it_starts",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.start_date} → {self.end_date})"
