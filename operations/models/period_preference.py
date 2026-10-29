"""تفضيلُ المعلّم لموضع الحصّة (W-20261010-032 مرحلة أ، D-330م).

فُصل من `schedule.py` لأنّه تجاوز حدّ حجم الملف (tests/test_file_size.py). ولا يقرؤه أيُّ محرّك بعد.
"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.academic_calendar import default_academic_year
from core.models import CustomUser, School

from .common import _uuid
from .schedule import ScheduleSlot


class TeacherPeriodPreference(models.Model):
    """تفضيلُ المعلّم لموضعِ حصّةٍ في الأسبوع: «أفضّلها» أو «أتجنّبها» (المرحلة أ من W-20261010-032، D-330م).

    الحالةُ المحايدةُ **لا تُخزَّن**: غيابُ الصفّ = محايدة، فلا يتضخّم الجدولُ بخمسٍ وثلاثين صفّاً لكلّ معلّم.
    ولا يقرؤه أيُّ محرّكٍ بعد: تُحفَظ الشبكةُ وتُعرَض وتُسجَّل في الأدمن، ويُوصَل الوزنُ بالمولّد في بطاقةٍ لاحقة.
    """

    PREFER = "prefer"
    AVOID = "avoid"
    CHOICES = [(PREFER, "أفضّلها"), (AVOID, "أتجنّبها")]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="teacher_period_preferences",
        verbose_name="المدرسة",
    )
    teacher = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="period_preferences",
        verbose_name="المعلم",
    )
    academic_year = models.CharField(
        max_length=9, default=default_academic_year, verbose_name="العام الدراسي"
    )
    day_of_week = models.PositiveSmallIntegerField(
        choices=ScheduleSlot.DAYS,
        validators=[MinValueValidator(0), MaxValueValidator(4)],
        verbose_name="اليوم",
    )
    period_number = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(ScheduleSlot.PERIODS_PER_DAY)],
        verbose_name="رقم الحصة",
    )
    preference = models.CharField(max_length=8, choices=CHOICES, verbose_name="التفضيل")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التعديل")

    class Meta:
        verbose_name = "تفضيل موضع حصة"
        verbose_name_plural = "تفضيلات مواضع الحصص"
        ordering = ["day_of_week", "period_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["teacher", "school", "academic_year", "day_of_week", "period_number"],
                name="unique_teacher_period_pref",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_preference_display()}: {self.get_day_of_week_display()} ح{self.period_number}"
