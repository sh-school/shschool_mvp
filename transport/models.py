"""
transport/models.py
نماذج النقل المدرسي — نُقلت من core/models.py
db_table مضبوط صراحةً لإبقاء نفس الجداول في قاعدة البيانات
"""
import uuid
from django.db import models
from .querysets import BusQuerySet, RouteQuerySet


def _uuid():
    return uuid.uuid4()


class SchoolBus(models.Model):
    """حافلة مدرسية — مع دعم Karwa ID وGPS"""
    objects = BusQuerySet.as_manager()

    id           = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school       = models.ForeignKey(
        'core.School', on_delete=models.CASCADE, related_name="buses"
    )
    bus_number   = models.CharField(max_length=20, verbose_name="رقم الحافلة")
    driver_name  = models.CharField(max_length=200, verbose_name="اسم السائق")
    driver_phone = models.CharField(max_length=20, verbose_name="جوال السائق")
    supervisor   = models.ForeignKey(
        'core.CustomUser', on_delete=models.SET_NULL, null=True,
        related_name="supervised_buses", verbose_name="مشرف الباص"
    )
    capacity     = models.PositiveIntegerField(default=30)
    karwa_id     = models.CharField(max_length=50, blank=True, verbose_name="رقم كروة (Karwa ID)")
    gps_link     = models.URLField(blank=True, verbose_name="رابط التتبع (GPS)")

    class Meta:
        verbose_name        = "حافلة مدرسية"
        verbose_name_plural = "الحافلات المدرسية"
        db_table            = "core_schoolbus"   # يبقي نفس الجدول الموجود

    def __str__(self):
        return f"Bus {self.bus_number} - {self.school.code}"


class BusRoute(models.Model):
    """خط سير حافلة — يربط مناطق بطلاب"""
    objects = RouteQuerySet.as_manager()

    id        = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    bus       = models.ForeignKey(SchoolBus, on_delete=models.CASCADE, related_name="routes")
    area_name = models.CharField(max_length=200, verbose_name="المنطقة")
    students  = models.ManyToManyField(
        'core.CustomUser', related_name="bus_routes", verbose_name="الطلاب"
    )

    class Meta:
        verbose_name        = "خط سير"
        verbose_name_plural = "خطوط السير"
        db_table            = "core_busroute"   # يبقي نفس الجدول الموجود

    def __str__(self):
        return f"{self.bus.bus_number} - {self.area_name}"
