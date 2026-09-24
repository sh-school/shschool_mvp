import uuid

from django.db import models

from core.models import CustomUser, School


class ImportLog(models.Model):
    STATUS = [
        ("pending", "قيد المعالجة"),
        ("validating", "جاري التحقق"),
        ("importing", "جاري الاستيراد"),
        ("completed", "مكتمل"),
        ("failed", "فشل"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, verbose_name="المدرسة")
    uploaded_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, verbose_name="رفعه"
    )
    file_name = models.CharField(max_length=255, verbose_name="اسم الملف")
    status = models.CharField(
        max_length=15, choices=STATUS, default="pending", verbose_name="الحالة"
    )
    total_rows = models.IntegerField(default=0, verbose_name="إجمالي الصفوف")
    imported_rows = models.IntegerField(default=0, verbose_name="الصفوف المستوردة")
    failed_rows = models.IntegerField(default=0, verbose_name="الصفوف الفاشلة")
    error_log = models.JSONField(default=list, blank=True, verbose_name="سجلّ الأخطاء")
    started_at = models.DateTimeField(auto_now_add=True, verbose_name="وقت البدء")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الاكتمال")

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "سجل استيراد"
        verbose_name_plural = "سجلات الاستيراد"

    def __str__(self):
        return f"{self.file_name} | {self.get_status_display()}"
