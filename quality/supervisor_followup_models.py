"""نماذجُ «نموذج 19 — متابعة أداء المشرف الإداري»: المتابعةُ ودرجاتُ مؤشراتها وتوصياتُها.

لا تقييمَ آليّاً ولا نسبةَ للموظّف. المؤشراتُ ثابتةٌ في `supervisor_followup_indicators` فلا جدولَ لها.
الجداولُ الثلاثةُ تحمل `school` بنفسها لعزل الصفّ المباشر في PostgreSQL.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import models
from django.utils import timezone

from core.models import CustomUser, School
from core.models.base import AllObjectsManager, AuditedModel, SoftDeleteManager

from .supervisor_followup_indicators import DEFAULT_CODE, FORMS, RATINGS, FollowUpForm

FOLLOWUP_STATUS = [
    ("draft", "مسودة"),
    ("saved", "محفوظة"),
    ("sent", "مُرسلة"),
    ("acknowledged", "أُقرّت"),
]

# ما تجاوز المسودة: يقرؤه المشرفُ ويُعدّ «متابعةً سابقة».
FINAL_STATUSES = ("saved", "sent", "acknowledged")

RECOMMENDATION_STATUS = [
    ("pending", "لم تُتابع بعد"),
    ("done", "نُفّذ"),
    ("not_done", "لم يُنفّذ"),
]


class _SoftDeletable(AuditedModel):
    """حذفٌ ناعمٌ فوق `AuditedModel` (كالزيارة الصفّية) كي تبقى أعمدةُ التدقيق."""

    is_deleted = models.BooleanField(default=False, db_index=True, verbose_name="محذوف")
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الحذف")

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    def delete(self, using: Any = None, keep_parents: bool = False) -> Any:
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at", "updated_by", "updated_at"])


class SupervisorFollowUp(_SoftDeletable):
    """متابعةٌ واحدةٌ لمشرفٍ إداريّ، ومعها لقطةُ غيابه واستئذانه وتأخّره للفترة المحسوبة."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="supervisor_followups",
        verbose_name="المدرسة",
    )
    supervisor = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name="supervisor_followups_received",
        verbose_name="المشرف الإداري",
    )
    follower = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name="supervisor_followups_made",
        verbose_name="المتابِع",
    )
    # بلا `choices`: استمارةٌ جديدةٌ تعريفٌ في الشيفرة لا هجرة.
    form_code = models.CharField(
        max_length=4, default=DEFAULT_CODE, db_default=DEFAULT_CODE, verbose_name="رقم النموذج"
    )
    follow_date = models.DateField(default=timezone.localdate, verbose_name="التاريخ")
    status = models.CharField(
        max_length=15, choices=FOLLOWUP_STATUS, default="draft", verbose_name="الحالة"
    )
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الإرسال")
    acknowledged_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الإقرار")
    supervisor_comment = models.TextField(
        blank=True, default="", db_default="", verbose_name="تعليق المشرف"
    )
    strengths = models.TextField(blank=True, verbose_name="جوانب القوة")
    improvements = models.TextField(blank=True, verbose_name="جوانب تحتاج إلى تحسين")

    period_start = models.DateField(null=True, blank=True, verbose_name="بداية الفترة المحسوبة")
    period_end = models.DateField(null=True, blank=True, verbose_name="نهاية الفترة المحسوبة")
    sick_days = models.PositiveSmallIntegerField(default=0, verbose_name="مرضي")
    casual_days = models.PositiveSmallIntegerField(default=0, verbose_name="عرضي")
    unpaid_days = models.PositiveSmallIntegerField(default=0, verbose_name="بلا راتب")
    permit_count = models.PositiveSmallIntegerField(default=0, verbose_name="الاستئذان")
    late_count = models.PositiveSmallIntegerField(default=0, verbose_name="التأخير الصباحي")

    class Meta:
        verbose_name = "متابعة مشرف إداري"
        verbose_name_plural = "متابعات المشرفين الإداريين"
        ordering = ["-follow_date", "-created_at"]
        indexes = [
            models.Index(fields=["school", "supervisor", "follow_date"], name="supfu_sup_date_idx"),
        ]
        constraints = [
            # مسودةٌ واحدةٌ للموظّف في كلّ استمارة: «متابعة جديدة» تفتحها بدل تكرارها.
            models.UniqueConstraint(
                fields=["school", "supervisor", "form_code"],
                condition=models.Q(status="draft", is_deleted=False),
                name="uniq_supfu_open_draft",
            ),
        ]

    @property
    def form(self) -> FollowUpForm:
        """تعريفُ استمارة هذه المتابعة."""
        return FORMS[self.form_code]

    @property
    def is_locked(self) -> bool:
        """بعد إقرار المشرف لا تعديلَ ولا حذف."""
        return self.status == "acknowledged"

    def __str__(self) -> str:
        return f"متابعة {str(self.pk)[:8]} — {self.follow_date}"


class SupervisorFollowUpScore(AuditedModel):
    """تقديرُ مؤشرٍ واحدٍ وملاحظتُه."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="+", verbose_name="المدرسة"
    )
    followup = models.ForeignKey(
        SupervisorFollowUp,
        on_delete=models.CASCADE,
        related_name="scores",
        verbose_name="المتابعة",
    )
    indicator_no = models.PositiveSmallIntegerField(verbose_name="رقم المؤشر")
    rating = models.CharField(max_length=15, choices=RATINGS, blank=True, verbose_name="التقدير")
    note = models.TextField(blank=True, verbose_name="ملاحظات")

    class Meta:
        verbose_name = "تقدير مؤشر متابعة"
        verbose_name_plural = "تقديرات مؤشرات المتابعة"
        ordering = ["indicator_no"]
        constraints = [
            models.UniqueConstraint(fields=["followup", "indicator_no"], name="uniq_supfu_score"),
        ]

    def __str__(self) -> str:
        return f"مؤشر {self.indicator_no}"


class SupervisorFollowUpRecommendation(_SoftDeletable):
    """توصيةٌ كُتبت في متابعة، وتُعلَّم منفَّذةً أو لا في متابعةٍ تالية (`reviewed_in`)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="+", verbose_name="المدرسة"
    )
    followup = models.ForeignKey(
        SupervisorFollowUp,
        on_delete=models.CASCADE,
        related_name="recommendations",
        verbose_name="المتابعة",
    )
    order = models.PositiveSmallIntegerField(default=0, verbose_name="الترتيب")
    text = models.TextField(verbose_name="التوصية")
    status = models.CharField(
        max_length=10,
        choices=RECOMMENDATION_STATUS,
        default="pending",
        verbose_name="حالة التنفيذ",
    )
    note = models.TextField(blank=True, verbose_name="الملاحظات")
    reviewed_in = models.ForeignKey(
        SupervisorFollowUp,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_recommendations",
        verbose_name="المتابعة التي تابعتها",
    )

    class Meta:
        verbose_name = "توصية متابعة"
        verbose_name_plural = "توصيات المتابعة"
        ordering = ["order", "created_at"]

    def __str__(self) -> str:
        return f"توصية {self.order}"
