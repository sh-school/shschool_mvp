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
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    uploaded_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    file_name = models.CharField(max_length=255)
    status = models.CharField(max_length=15, choices=STATUS, default="pending")
    total_rows = models.IntegerField(default=0)
    imported_rows = models.IntegerField(default=0)
    failed_rows = models.IntegerField(default=0)
    error_log = models.JSONField(default=list, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "سجل استيراد"

    def __str__(self):
        return f"{self.file_name} | {self.get_status_display()}"
