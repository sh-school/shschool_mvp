"""نماذجُ المعرفة المحلّيّة — وثيقةٌ ومقاطعُها المضمَّنة، مقيَّدتان بالمدرسة (RLS في الهجرة 0002).

`KnowledgeDocument` وثيقةُ معرفةٍ عامّة (تعميمٌ، سياسةٌ، خطّةٌ فصليّة، دليلٌ) ترفعها القيادةُ
ليسأل عنها الموظّفون. **ليست مكاناً لسجلّات الطلبة**: المساعدُ يجيب من هذه الوثائق وحدَها.

`DocumentChunk` مقطعٌ من الوثيقة مع متّجه تضمينه (JSON من الأعداد العشريّة؛ bge-m3 يعطي 1024
بُعداً). البحثُ بجيب التمام في بايثون/NumPy — كافٍ لآلاف المقاطع لكلّ مدرسة، ويُستبدل بـpgvector
حين يكبر الحجمُ بلا تغييرٍ في الواجهة (`services.rag`).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from core.models.base import SchoolScopedModel


class KnowledgeDocument(SchoolScopedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "بانتظار الفهرسة"
        INDEXING = "indexing", "قيد الفهرسة"
        READY = "ready", "جاهز"
        FAILED = "failed", "فشل"

    title = models.CharField(max_length=200, verbose_name="العنوان")
    file = models.FileField(upload_to="local_ai/%Y/%m/", verbose_name="الملفّ")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="local_ai_documents",
        verbose_name="رفعه",
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, verbose_name="الحالة"
    )
    error_message = models.TextField(blank=True, default="", verbose_name="سببُ الفشل")
    #: ملخّصٌ تلقائيٌّ (الأتمتة: بعد الفهرسة) يظهر في القائمة ويُستعمل في ترشيح المراجع.
    summary = models.TextField(blank=True, default="", verbose_name="الملخّص")
    #: بياناتٌ منظَّمةٌ مستخرَجةٌ تلقائيّاً (جهةُ الإصدار، التاريخ، المستهدفون، المواعيد…).
    metadata = models.JSONField(default=dict, blank=True, verbose_name="بيانات مستخرَجة")
    chunk_count = models.PositiveIntegerField(default=0, verbose_name="عددُ المقاطع")
    indexed_at = models.DateTimeField(null=True, blank=True, verbose_name="وقتُ الفهرسة")
    is_active = models.BooleanField(default=True, verbose_name="مفعَّلة")

    class Meta(SchoolScopedModel.Meta):
        verbose_name = "وثيقة معرفة"
        verbose_name_plural = "وثائق المعرفة"
        indexes = [models.Index(fields=["school", "status"], name="local_ai_doc_school_status")]

    def __str__(self) -> str:
        return self.title

    @property
    def filename(self) -> str:
        return self.file.name.rsplit("/", 1)[-1] if self.file else ""

    def mark_failed(self, reason: str) -> None:
        self.status = self.Status.FAILED
        self.error_message = reason[:2000]
        self.save(update_fields=["status", "error_message", "updated_at"])


class DocumentChunk(models.Model):
    school = models.ForeignKey(
        "core.School",
        on_delete=models.CASCADE,
        related_name="local_ai_chunks",
        verbose_name="المدرسة",
    )
    document = models.ForeignKey(
        KnowledgeDocument, on_delete=models.CASCADE, related_name="chunks", verbose_name="الوثيقة"
    )
    ordinal = models.PositiveIntegerField(verbose_name="الترتيب")
    text = models.TextField(verbose_name="النصّ")
    char_count = models.PositiveIntegerField(default=0, verbose_name="عددُ الحروف")
    embedding = models.JSONField(verbose_name="متّجه التضمين")

    class Meta:
        verbose_name = "مقطع وثيقة"
        verbose_name_plural = "مقاطع الوثائق"
        ordering = ["document", "ordinal"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "ordinal"], name="local_ai_chunk_unique_ordinal"
            )
        ]

    def __str__(self) -> str:
        return f"{self.document_id}#{self.ordinal}"
