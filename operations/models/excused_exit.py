"""وسمُ «خروجٍ مبرَّرٍ دائم» لطالبٍ بمدّة (قرارُ المالك 2026-11-19، إدارةُ الأجنحة 3/4).

يضعه الممرّضُ أو الأخصائيُّ (اجتماعيٌّ أو نفسيّ) لطالبٍ تقتضي حالتُه الخروجَ المتكرّر؛ فيُسقط عنه **تأخّرَ العودة**
وحدَه (لا الخروجَ ولا دقائقَه). السببُ بيانٌ صحّيٌّ لقاصر: يراه واضعُه فقط، ولا يخرج في أيّ شاشةِ مشرفٍ أو قيادةٍ
ولا في إشعارٍ ولا سجلّ؛ والمشرفُ يعرف **وجودَ الوسم** لا سببَه.
"""

import uuid

from django.db import models

from core.models import CustomUser, School


class ExcusedExit(models.Model):
    """وسمٌ لطالبٍ من `starts_on` إلى `ends_on` شاملةً — المدّةُ شرطٌ فلا وسمَ مفتوحَ النهاية."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="excused_exits", verbose_name="المدرسة"
    )
    student = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="excused_exits",
        verbose_name="الطالب",
    )
    starts_on = models.DateField(verbose_name="من")
    ends_on = models.DateField(verbose_name="إلى")
    set_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="excused_exits_set",
        verbose_name="وضعه",
    )
    set_by_role = models.CharField(max_length=20, verbose_name="دورُ واضعه")
    reason = models.TextField(blank=True, verbose_name="السبب (لواضعه وحدَه)")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="وُضع في")

    class Meta:
        verbose_name = "خروجٌ مبرَّرٌ دائم"
        verbose_name_plural = "خروجٌ مبرَّرٌ دائم"
        indexes = [
            models.Index(fields=["school", "student", "ends_on"], name="excused_exit_student_idx")
        ]
        constraints = [
            models.CheckConstraint(  # type: ignore[call-arg]  # `condition` (Django 5.1+) غيرُ معروفٍ لـdjango-stubs 5.0
                condition=models.Q(ends_on__gte=models.F("starts_on")),
                name="excused_exit_range_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.starts_on} → {self.ends_on}"
