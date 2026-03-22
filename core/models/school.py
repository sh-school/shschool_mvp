import uuid
from django.db import models


def _uuid():
    return uuid.uuid4()


class School(models.Model):
    id         = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    name       = models.CharField(max_length=200, verbose_name="اسم المدرسة")
    code       = models.CharField(max_length=10, unique=True, verbose_name="الكود")
    city       = models.CharField(max_length=100, verbose_name="المدينة", default="الشحانية")
    phone      = models.CharField(max_length=20, blank=True)
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "مدرسة"
        verbose_name_plural = "المدارس"

    def __str__(self):
        return f"{self.name} ({self.code})"
