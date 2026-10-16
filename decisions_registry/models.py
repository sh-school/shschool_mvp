from django.db import models


class ImportBatch(models.Model):
    """دفعةُ استيرادٍ واحدة: بصمةُ الملفّين وأعدادُ ما قُرئ وما أُنشئ — تدقيقٌ لا بيانات."""

    file_fingerprint = models.CharField("بصمة الملفّين", max_length=64, db_index=True)
    row_count = models.PositiveIntegerField("الصفوف المقروءة")
    created_count = models.PositiveIntegerField("المُنشأ")
    names_masked = models.BooleanField("حُجبت أسماءٌ من قائمة", default=False)
    imported_at = models.DateTimeField("وقت الاستيراد", auto_now_add=True)

    class Meta:
        verbose_name = "دفعة استيراد قرارات"
        verbose_name_plural = "دفعات استيراد القرارات"
        ordering = ["-imported_at"]

    def __str__(self) -> str:
        return f"{self.imported_at:%Y-%m-%d %H:%M} · {self.created_count}/{self.row_count}"


class Decision(models.Model):
    """قرارُ مالكٍ للقراءة فقط، مستوردٌ باتجاهٍ واحد؛ لا يُعدَّل ولا يُكتب منه إلى المصدر."""

    KIND_CHOICES = [("approval", "اعتماد"), ("structural", "بنيوي")]

    decision_id = models.CharField("المعرّف", max_length=64, unique=True)
    decided_at_text = models.CharField("التاريخ كما في المصدر", max_length=64, blank=True)
    text = models.TextField("النصّ (بعد حجب الشخصيّ)")
    effect = models.TextField("الأثر", blank=True)
    reference = models.CharField("المرجع", max_length=255, blank=True)
    kind = models.CharField("النوع", max_length=16, choices=KIND_CHOICES, blank=True)
    location = models.CharField("الموضع", max_length=255, blank=True)
    source_ts = models.CharField("وقت الوصف الوصفي", max_length=40, blank=True)
    fingerprint = models.CharField("البصمة", max_length=64, db_index=True)
    batch = models.ForeignKey(
        ImportBatch, on_delete=models.PROTECT, related_name="decisions", verbose_name="الدفعة"
    )
    imported_at = models.DateTimeField("وقت الاستيراد", auto_now_add=True)

    class Meta:
        verbose_name = "قرار مالك"
        verbose_name_plural = "قرارات المالك"
        ordering = ["decision_id"]

    def __str__(self) -> str:
        return self.decision_id
