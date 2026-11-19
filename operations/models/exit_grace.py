"""مهلةُ العودة لكلّ وجهةِ خروجٍ — إعدادٌ مدرسيّ (قرارُ المالك 2026-11-19، إدارةُ الأجنحة 2/4).

سطرٌ لكلّ (مدرسة، وجهة). الوجهةُ بلا سطرٍ بلا مهلة: لا رقمَ افتراضيّاً يُخمَّن، فالمدرسةُ تضبطه.
والعيادةُ والإدارةُ والنائبُ والمنسّقُ بلا مهلةٍ أصلاً فلا تُعرض للضبط (`exit_card.GRACE_DESTINATIONS`).
"""

import uuid

from django.db import models

from core.models import School


class ExitDestinationGrace(models.Model):
    """دقائقُ المهلة المسموحة بين «وصل» و«عاد» لوجهةٍ في مدرسة."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="exit_graces", verbose_name="المدرسة"
    )
    destination = models.CharField(max_length=10, verbose_name="الوجهة")
    minutes = models.PositiveSmallIntegerField(verbose_name="المهلة (دقائق)")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرُ تحديث")

    class Meta:
        verbose_name = "مهلةُ وجهةِ خروج"
        verbose_name_plural = "مُهَلُ وجهات الخروج"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "destination"], name="uniq_exit_grace_school_destination"
            ),
            models.CheckConstraint(  # type: ignore[call-arg]  # `condition` (Django 5.1+) غيرُ معروفٍ لـdjango-stubs 5.0
                condition=models.Q(minutes__gte=1), name="exit_grace_minutes_positive"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.destination} · {self.minutes} د"
