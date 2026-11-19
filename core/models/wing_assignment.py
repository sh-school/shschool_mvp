"""تعيينُ مشرف الجناح وميدانيِّه — سجلٌّ زمنيٌّ (W-20261119-001، المرحلةُ 1 من 4)."""

import datetime
from typing import Any

from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import RangeBoundary, RangeOperators
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, QuerySet

from .academic import DateRange
from .school import _uuid
from .user import CustomUser
from .wing_holders import WING_ROLES


def _overlapping(
    rows: QuerySet[Any], start: datetime.date, end: datetime.date | None
) -> QuerySet[Any]:
    """ما يتداخل من `rows` مع المدّة [start, end] (نهايةٌ فارغةٌ = مفتوحة)."""
    rows = rows.filter(Q(end_date__isnull=True) | Q(end_date__gte=start))
    return rows.filter(start_date__lte=end) if end else rows


class WingAssignment(models.Model):
    """تعيينُ مشرف جناحٍ أو ميدانيِّه — سجلٌّ زمنيٌّ لا حقلٌ يُكتب فوق سابقه.

    من حمل الجناحَ أمسِ يجب أن يُعرف بعد تغيير التعيين (غيابُ الأسبوع الماضي يُقرأ
    بمشرفه يومَه)، فالتعيينُ الجديد **يغلق** السابقَ بتاريخٍ ولا يحذفه.

    ثلاثةُ قيودِ استبعادٍ في القاعدة (لا `clean()` وحدَه: كتابتان متزامنتان تمرّان عليه معاً):
    حاملٌ واحدٌ لكلّ (جناح، دور) في اليوم؛ ولا يحمل الشخصُ الدورَ نفسَه في جناحين؛
    ولا يحمل دورين في جناحٍ واحد. ويجوز له دورانِ مختلفان في جناحين مختلفين.
    """

    #: من يصلح للتعيين — بالدور لا بالمسمّى (كـ`WingCoverage.SUBSTITUTE_ROLES`).
    ELIGIBLE_ROLES = ("admin_supervisor", "vice_admin", "student_observer")

    #: من يعيّن: المدير والنائبُ الإداريّ ومنسّقُ شؤون الطلبة (قرارُ المالك 2026-11-19).
    ASSIGNER_ROLES = ("principal", "vice_admin", "student_affairs_coordinator")

    ROLES = WING_ROLES

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    wing = models.ForeignKey(
        "core.Wing", on_delete=models.CASCADE, related_name="assignments", verbose_name="الجناح"
    )
    role = models.CharField(max_length=20, choices=WING_ROLES, verbose_name="الدور")
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name="wing_assignments",
        verbose_name="المعيَّن",
    )
    start_date = models.DateField(verbose_name="من")
    #: فارغةٌ = مفتوحةٌ حتّى يحلّ محلَّها تعيينٌ جديد.
    end_date = models.DateField(null=True, blank=True, verbose_name="إلى")
    assigned_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wing_assignments_made",
        verbose_name="عيّنه",
    )
    ended_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wing_assignments_ended",
        verbose_name="أنهاه",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "تعيينُ جناح"
        verbose_name_plural = "تعيينات الأجنحة"
        ordering = ["-start_date"]
        constraints = [
            models.CheckConstraint(  # type: ignore[call-arg]
                condition=Q(end_date__isnull=True) | Q(end_date__gte=models.F("start_date")),
                name="wing_assignment_ends_after_it_starts",
            ),
            *[
                ExclusionConstraint(
                    name=name,
                    expressions=[
                        (
                            DateRange(
                                "start_date", "end_date", RangeBoundary(inclusive_upper=True)
                            ),
                            RangeOperators.OVERLAPS,
                        ),
                        *[(field, RangeOperators.EQUAL) for field in fields],
                    ],
                )
                for name, fields in (
                    ("no_overlapping_wing_assignment", ("wing", "role")),
                    ("no_user_same_role_in_two_wings", ("user", "role")),
                    ("no_user_two_roles_in_one_wing", ("user", "wing")),
                )
            ],
        ]
        indexes = [
            models.Index(fields=["wing", "role", "start_date"], name="core_wingas_wing_role_idx")
        ]

    def covers(self, day: datetime.date) -> bool:
        return self.start_date <= day and (self.end_date is None or day <= self.end_date)

    def clean(self) -> None:
        """أهليّةُ المعيَّن، ثمّ ما يرفضه القيدُ بلا بيان: دورانِ في جناحٍ، أو الدورُ نفسُه في جناحين."""
        super().clean()
        errors = {}
        if self.end_date and self.start_date and self.end_date < self.start_date:
            errors["end_date"] = "النهايةُ قبل البداية."
        if self.user_id and self.wing_id:
            from .access import Membership

            eligible = Membership.objects.filter(
                user_id=self.user_id,
                school_id=self.wing.school_id,
                is_active=True,
                role__name__in=self.ELIGIBLE_ROLES,
            ).exists()
            if not eligible:
                errors["user"] = "المعيَّنُ مشرفٌ إداريٌّ أو النائبُ الإداريّ أو ملاحظُ طلبة."
            elif self.start_date:
                mine = WingAssignment.objects.filter(user_id=self.user_id).exclude(pk=self.pk)
                clash = _overlapping(mine, self.start_date, self.end_date)
                if clash.filter(wing_id=self.wing_id).exists():
                    errors["user"] = "يحمل دوراً آخر في هذا الجناح في المدّة نفسها."
                elif clash.filter(role=self.role).exclude(wing_id=self.wing_id).exists():
                    errors["user"] = "يحمل الدورَ نفسَه في جناحٍ آخر في المدّة نفسها."
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        end = f"{self.end_date}" if self.end_date else "مفتوح"
        return f"{self.wing.name}: {self.get_role_display()} ({self.start_date} → {end})"
