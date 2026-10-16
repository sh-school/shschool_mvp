"""عضويّةُ الطالب في مجموعةٍ اختياريّةٍ متوازية (W-20261002-021، يُنهي الخطرَ المقبول مؤقّتاً بقرار D-129م).

كان `Session.elective_group` وسماً نصّيّاً فقط، فيرى معلّمُ الجلسة الاختياريّة طلبةَ الشعبة كلَّهم.
هذا النموذجُ يربط قيدَ الطالب بوسم المجموعة نفسِه (نصٌّ كما في `ScheduleSlot.elective_group`).
توسيعٌ لا تقليص: الوسمُ القديم قائمٌ غيرُ مستعمل، وغيابُ العضويّة يرجع إلى سلوك الشعبة كلّها.
"""

from django.db import models

from .academic import StudentEnrollment
from .school import _uuid


class ElectiveGroupMembership(models.Model):
    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    enrollment = models.ForeignKey(
        StudentEnrollment,
        on_delete=models.CASCADE,
        related_name="elective_memberships",
        verbose_name="قيد الطالب",
    )
    group_label = models.CharField(
        max_length=40,
        verbose_name="وسم المجموعة الاختيارية",
        help_text="النصُّ نفسُه في `Session.elective_group` و`ScheduleSlot.elective_group`.",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "عضويّة مجموعة اختياريّة"
        verbose_name_plural = "عضويّات المجموعات الاختياريّة"
        constraints = [
            models.UniqueConstraint(
                fields=["enrollment", "group_label"], name="unique_elective_membership"
            )
        ]
        indexes = [models.Index(fields=["group_label"], name="idx_elective_label")]

    def __str__(self) -> str:
        return f"{self.enrollment.student.full_name} ∈ {self.group_label}"
