"""اقتراحاتُ المخالفة 1-01 لغيابٍ أو تأخّرٍ بين الحصص — طابورٌ يعتمده مشرفُ جناح الطالب (W-20261013-034).

المداومُ الذي غاب حصّةً بلا عذر ولم يكن غيابُه بين حضورين (2-02) ولا حتى آخر اليوم (3-10) لا تُنشأ له مخالفةٌ آلياً.
فيُقترح له **سطرٌ واحدٌ لكلّ طالبٍ في اليوم** (قرارُ المالك 2)، يظهر لمشرفه بعد مهلة العذر (يومان دراسيّان) لا فور الرصد،
وبقراره وحده تُنشأ المخالفةُ عبر `BehaviorService` بلا نقاطٍ ولا قرارٍ ولا إرسالٍ لوليّ الأمر (D-272م).
"""

from __future__ import annotations

import uuid

from django.db import models

from core.models import CustomUser, School


class ConductProposal(models.Model):
    KINDS = [
        ("absence", "غيابُ حصّة"),
        ("tardy", "تأخّرٌ بين الحصص"),
    ]
    STATUSES = [
        ("proposed", "مقترح"),
        ("approved", "معتمَد"),
        ("rejected", "مردود"),
        ("withdrawn", "مسحوب"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name="conduct_proposals",
        verbose_name="المدرسة",
    )
    student = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name="conduct_proposals",
        verbose_name="الطالب",
    )
    date = models.DateField(verbose_name="يومُ الواقعة")
    kind = models.CharField(max_length=10, choices=KINDS, verbose_name="النوع")
    #: بدءُ الحصص الواقعة (HH:MM) مرتّبةً — الخانةُ الزمنيّة لا الحصّة، فزوجُ الاختيار حصّةٌ واحدة.
    periods = models.JSONField(default=list, verbose_name="الحصص")
    note = models.TextField(blank=True, default="", verbose_name="ملاحظة (الحصص والمواد)")
    status = models.CharField(
        max_length=10, choices=STATUSES, default="proposed", db_index=True, verbose_name="الحالة"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الاقتراح")
    decided_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conduct_proposals_decided",
        verbose_name="من قرّر",
    )
    decided_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ القرار")
    #: المخالفةُ التي أنشأها الاعتماد — لا تُمسّ بسحبٍ لاحق (افتراض المواصفة).
    infraction = models.OneToOneField(
        "behavior.BehaviorInfraction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conduct_proposal",
        verbose_name="المخالفة المنشأة",
    )

    class Meta:
        verbose_name = "اقتراح مخالفة"
        verbose_name_plural = "اقتراحات المخالفات"
        ordering = ["-date", "student_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "student", "date"], name="uniq_conduct_proposal_student_day"
            )
        ]
        indexes = [models.Index(fields=["school", "status", "date"], name="conductprop_queue_idx")]

    def __str__(self) -> str:
        return f"{self.student_id} · {self.date} · {self.get_kind_display()} · {self.get_status_display()}"


class ReturnLateSuggestion(models.Model):
    """اقتراحُ متابعةٍ لتأخّر عودة الطالب من الخروج في أسبوعٍ دراسيّ (إدارةُ الأجنحة 4/4، W-20261119-004).

    على نمط `ConductProposal`: يولّده النظامُ ويقرّره مشرفُ جناح الطالب قبولاً أو رفضاً، **ولا مخالفةَ آليّة**
    ولا أثرَ على وليّ الأمر. **اقتراحٌ واحدٌ لكلّ طالبٍ في الأسبوع** (القيدُ الفريد) فيُعاد التشغيلُ بلا تكرار.
    """

    STATUSES = [
        ("proposed", "مقترح"),
        ("accepted", "مقبول"),
        ("dismissed", "مرفوض"),
        ("withdrawn", "مسحوب"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name="return_late_suggestions",
        verbose_name="المدرسة",
    )
    student = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name="return_late_suggestions",
        verbose_name="الطالب",
    )
    week_start = models.DateField(verbose_name="أحدُ الأسبوع")
    late_minutes = models.PositiveIntegerField(default=0, verbose_name="مجموعُ دقائق تأخّر العودة")
    exit_count = models.PositiveIntegerField(default=0, verbose_name="مرّاتُ الخروج")
    status = models.CharField(
        max_length=10, choices=STATUSES, default="proposed", db_index=True, verbose_name="الحالة"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الاقتراح")
    decided_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="return_late_suggestions_decided",
        verbose_name="من قرّر",
    )
    decided_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ القرار")

    class Meta:
        verbose_name = "اقتراح متابعة تأخّر العودة"
        verbose_name_plural = "اقتراحات متابعة تأخّر العودة"
        ordering = ["-week_start", "student_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "student", "week_start"], name="uniq_return_late_student_week"
            )
        ]
        indexes = [
            models.Index(fields=["school", "status", "week_start"], name="retlate_queue_idx")
        ]

    def __str__(self) -> str:
        return f"{self.student_id} · {self.week_start} · {self.late_minutes} · {self.get_status_display()}"
