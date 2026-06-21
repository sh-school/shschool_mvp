"""
core/models/stored_file.py
تخزين الملفات المرفوعة داخل قاعدة البيانات (بديل نظام الملفات المؤقّت على Railway).

السبب: حاوية الويب على Railway بلا قرص دائم — أي ملف في /app/media يُفقَد عند
إعادة النشر. حفظ الملف كـ binary في PostgreSQL يجعله يدوم ويُنسَخ احتياطياً مع القاعدة.
مناسب للملفات الصغيرة (أعذار، أدلة، مرفقات). للملفات الكبيرة يُفضَّل S3/R2 (USE_S3).
"""

from django.db import models


class StoredFile(models.Model):
    name = models.CharField(
        max_length=500, unique=True, db_index=True, verbose_name="المسار (مفتاح التخزين)"
    )
    content = models.BinaryField(verbose_name="المحتوى")
    size = models.PositiveIntegerField(default=0, verbose_name="الحجم (بايت)")
    content_type = models.CharField(max_length=200, blank=True, verbose_name="نوع المحتوى")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "ملف مُخزَّن"
        verbose_name_plural = "الملفات المُخزَّنة"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name
