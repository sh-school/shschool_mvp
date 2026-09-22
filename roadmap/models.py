"""خارطةُ تجويد المنصّة — بنودٌ ومؤشّراتٌ وقراراتٌ ومخاطرُ وقائمةُ فحص.

نماذجُ نحيلة: الحقولُ والقيودُ وحدَها. قواعدُ التحقّق والحسابُ والتدقيقُ في
`services.py`، والقراءةُ في `selectors.py`.

**ليست بياناتِ مدرسةٍ ولا أشخاص**: الخارطةُ وثيقةُ مطوّرِ المنصّة عن المنصّة نفسها،
فلا `school` في أيٍّ منها ولا سياسةَ RLS عليها (انظر `core/tenancy.py::GLOBAL_INFRASTRUCTURE`).
والمفتاحُ الطبيعيّ `code` نصٌّ فريد (`U-01`، `MK1`، `D-05`…) — يقوم عليه الاستيرادُ المتكرّر.
"""

from django.conf import settings
from django.db import models


class Stamped(models.Model):
    """طوابعُ الإنشاء والتعديل ومن عدّل."""

    created_at = models.DateTimeField("أُنشئ", auto_now_add=True)
    updated_at = models.DateTimeField("عُدِّل", auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="عدّله",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        abstract = True


class ItemStatus(models.TextChoices):
    TODO = "todo", "لم يبدأ"
    DOING = "doing", "قيد التنفيذ"
    DONE = "done", "مُغلَق"
    BLOCKED = "blocked", "محجوب"
    DEFERRED = "deferred", "مؤجّل"


class DecisionStatus(models.TextChoices):
    OPEN = "open", "مفتوح"
    DECIDED = "decided", "محسوم"
    DEFERRED = "deferred", "مؤجَّل"


class KpiDirection(models.TextChoices):
    DOWN = "down", "الأقلُّ أفضل"
    UP = "up", "الأعلى أفضل"
    FLOOR = "floor", "حدٌّ أدنى"


class RoadmapItem(Stamped):
    """بندٌ في الجدول الزمنيّ (`U-01`، `M-03`، `VI-12`…)."""

    code = models.CharField("الرمز", max_length=32, unique=True)
    src = models.CharField("المصدر", max_length=16, blank=True)
    lane = models.CharField("المسار", max_length=32, db_index=True)
    title = models.TextField("العنوان")
    status = models.CharField(
        "الحالة", max_length=16, choices=ItemStatus.choices, default=ItemStatus.TODO
    )
    progress = models.PositiveSmallIntegerField("التقدّم %", default=0)
    start_date = models.DateField("البداية", null=True, blank=True)
    end_date = models.DateField("النهاية", null=True, blank=True)
    date_basis = models.CharField("أساس التاريخ", max_length=120, blank=True)
    effort = models.FloatField("الجهد (أيّام)", default=1)
    deps = models.CharField("الاعتماديّات", max_length=255, blank=True)
    criterion = models.TextField("معيار الإغلاق", blank=True)
    note = models.TextField("ملاحظة", blank=True)
    gate = models.CharField("البوّابة", max_length=32, blank=True)
    ref = models.CharField("المرجع", max_length=255, blank=True)
    pr = models.CharField("طلب الدمج", max_length=64, blank=True)
    sort_order = models.IntegerField("الترتيب", default=0)

    class Meta:
        ordering = ["sort_order", "code"]
        verbose_name = "بندُ خارطة"
        verbose_name_plural = "بنودُ الخارطة"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(progress__gte=0, progress__lte=100),
                name="roadmap_item_progress_0_100",
            ),
        ]

    def __str__(self) -> str:
        return self.code


class RoadmapKpi(Stamped):
    """مؤشّرٌ بخطّ أساسٍ وقيمةٍ حاليّةٍ وهدف. القيمُ العدديّةُ قد تكون فارغةً (لم يُقَس)."""

    code = models.CharField("الرمز", max_length=32, unique=True)
    lane = models.CharField("المسار", max_length=32, db_index=True)
    name = models.CharField("المؤشّر", max_length=255)
    baseline = models.FloatField("الأساس", null=True, blank=True)
    current = models.FloatField("الحاليّ", null=True, blank=True)
    target = models.FloatField("الهدف", null=True, blank=True)
    baseline_text = models.CharField("الأساس (نصّاً)", max_length=255, blank=True)
    target_text = models.CharField("الهدف (نصّاً)", max_length=255, blank=True)
    direction = models.CharField(
        "الاتّجاه", max_length=8, choices=KpiDirection.choices, default=KpiDirection.DOWN
    )
    unit = models.CharField("الوحدة", max_length=16, blank=True)
    source = models.CharField("المصدر", max_length=255, blank=True)
    why = models.TextField("سببُ غياب القياس", blank=True)
    text_mode = models.BooleanField("قيمٌ نصّيّة", default=False)
    measured_at = models.DateField("تاريخ القياس", null=True, blank=True)
    history = models.JSONField("السجلّ", default=list, blank=True)
    #: حقولٌ متغيّرةُ الشكل من المصدر (affected، basis، dim، method، ref، track…).
    extra = models.JSONField("أخرى", default=dict, blank=True)
    sort_order = models.IntegerField("الترتيب", default=0)

    class Meta:
        ordering = ["sort_order", "code"]
        verbose_name = "مؤشّرُ خارطة"
        verbose_name_plural = "مؤشّراتُ الخارطة"

    def __str__(self) -> str:
        return self.code


class RoadmapDecision(Stamped):
    """قرارٌ يحجب بنداً أو مرحلة (`D-01`، `MD3`…)."""

    code = models.CharField("الرمز", max_length=32, unique=True)
    src = models.CharField("المصدر", max_length=16, blank=True)
    title = models.TextField("القرار")
    status = models.CharField(
        "الحالة", max_length=16, choices=DecisionStatus.choices, default=DecisionStatus.OPEN
    )
    decider = models.CharField("صاحبُ القرار", max_length=64, blank=True)
    due = models.CharField("الموعد", max_length=255, blank=True)
    decision_date = models.DateField("تاريخُ الحسم", null=True, blank=True)
    blocks = models.TextField("يحجب", blank=True)
    options = models.TextField("الخيارات", blank=True)
    recommendation = models.TextField("التوصية", blank=True)
    sort_order = models.IntegerField("الترتيب", default=0)

    class Meta:
        ordering = ["sort_order", "code"]
        verbose_name = "قرارُ خارطة"
        verbose_name_plural = "قراراتُ الخارطة"

    def __str__(self) -> str:
        return self.code


class RoadmapRisk(Stamped):
    code = models.CharField("الرمز", max_length=32, unique=True)
    src = models.CharField("المصدر", max_length=255, blank=True)
    risk = models.TextField("المخاطرة")
    prob = models.CharField("الاحتمال", max_length=32, blank=True)
    impact = models.CharField("الأثر", max_length=32, blank=True)
    mitigation = models.TextField("التخفيف", blank=True)
    sort_order = models.IntegerField("الترتيب", default=0)

    class Meta:
        ordering = ["sort_order", "code"]
        verbose_name = "مخاطرةٌ في الخارطة"
        verbose_name_plural = "مخاطرُ الخارطة"

    def __str__(self) -> str:
        return self.code


class RoadmapChecklistItem(Stamped):
    """بندٌ في قائمة فحص الجهاز الحقيقيّ (للمالك قبل نشر كلّ مرحلة)."""

    code = models.CharField("الرمز", max_length=32, unique=True)
    src = models.CharField("المصدر", max_length=255, blank=True)
    text = models.TextField("النصّ")
    done = models.BooleanField("أُنجز", default=False)
    sort_order = models.IntegerField("الترتيب", default=0)

    class Meta:
        ordering = ["sort_order", "code"]
        verbose_name = "بندُ قائمة فحص"
        verbose_name_plural = "قائمةُ فحص الجهاز"

    def __str__(self) -> str:
        return self.code


class RoadmapMeta(Stamped):
    """وثيقةٌ مفردةٌ: المسارات والمراحل والمحطّات والمعايير والقواعد ونوافذُ التنفيذ.

    JSON لأنّ شكلَها قوائمُ متباينةُ العناصر (أزواجٌ ونصوصٌ وكائنات) تُعرض كما هي
    ولا يُستعلم عنها؛ والمفتاحُ يبقى وثيقةً واحدةً (`roadmap`).
    """

    KEY = "roadmap"

    key = models.CharField("المفتاح", max_length=32, unique=True, default=KEY)
    data = models.JSONField("المحتوى", default=dict, blank=True)

    class Meta:
        verbose_name = "وثيقةُ الخارطة"
        verbose_name_plural = "وثائقُ الخارطة"

    def __str__(self) -> str:
        return self.key
