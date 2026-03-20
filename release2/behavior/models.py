"""
behavior/models.py
نماذج السلوك الطلابي — نُقلت من core/models.py
db_table مضبوط صراحةً لإبقاء نفس الجداول في قاعدة البيانات
"""
import uuid
from django.db import models


def _uuid():
    return uuid.uuid4()


class BehaviorInfraction(models.Model):
    """مخالفة سلوكية — 4 درجات وفق لائحة وزارة التعليم القطرية"""
    LEVELS = [
        (1, 'الدرجة الأولى (بسيطة)'),
        (2, 'الدرجة الثانية (متوسطة)'),
        (3, 'الدرجة الثالثة (جسيمة)'),
        (4, 'الدرجة الرابعة (شديدة الخطورة)'),
    ]
    id              = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school          = models.ForeignKey('core.School', on_delete=models.CASCADE)
    student         = models.ForeignKey(
        'core.CustomUser', on_delete=models.CASCADE, related_name="behavior_infractions"
    )
    reported_by     = models.ForeignKey(
        'core.CustomUser', on_delete=models.SET_NULL, null=True, related_name="reported_infractions"
    )
    date            = models.DateField(auto_now_add=True)
    created_at      = models.DateTimeField(auto_now_add=True, null=True)
    level           = models.PositiveSmallIntegerField(choices=LEVELS, default=1)
    description     = models.TextField(verbose_name="وصف المخالفة")
    action_taken    = models.TextField(blank=True, verbose_name="الإجراء المتخذ")
    points_deducted = models.PositiveIntegerField(default=0, verbose_name="النقاط المخصومة")
    is_resolved     = models.BooleanField(default=False)

    class Meta:
        verbose_name        = "مخالفة سلوكية"
        verbose_name_plural = "المخالفات السلوكية"
        ordering            = ['-date', '-created_at']
        db_table            = "core_behaviorinfraction"   # يبقي نفس الجدول الموجود

    def __str__(self):
        return f"{self.student.full_name} - {self.get_level_display()}"


class BehaviorPointRecovery(models.Model):
    """استعادة نقاط السلوك — التعزيز الإيجابي"""
    id              = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    infraction      = models.OneToOneField(
        BehaviorInfraction, on_delete=models.CASCADE, related_name="recovery"
    )
    reason          = models.TextField(verbose_name="سبب استعادة النقاط (سلوك إيجابي)")
    points_restored = models.PositiveIntegerField(default=0)
    approved_by     = models.ForeignKey(
        'core.CustomUser', on_delete=models.SET_NULL, null=True
    )
    date            = models.DateField(auto_now_add=True)

    class Meta:
        verbose_name        = "استعادة نقاط"
        verbose_name_plural = "استعادة النقاط"
        db_table            = "core_behaviorpointrecovery"   # يبقي نفس الجدول الموجود

    def __str__(self):
        return f"Recovery: {self.infraction.student.full_name} (+{self.points_restored})"
