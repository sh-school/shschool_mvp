"""
quality/observation_models.py
الإشراف على أداء المعلّم — استمارة الملاحظة الصفّية (Classroom Observation).

تكوينية لكل زيارة/حصة (مكمّلة لتقييم الموظف السنوي EmployeeEvaluation الذي هو
تجميعي/سنوي). مصدرها الرسمي: استمارة الإشراف على أداء المعلّم (وزارة التعليم — قطر).

الهيكل: ObservationCriterion (معايير ثابتة مزروعة، 4 مجالات) →
        ClassroomObservation (زيارة) → ObservationScore (تقييم معيار + توصية).
"""

import uuid

from django.db import models
from django.utils import timezone

from core.models import CustomUser, School
from core.models.base import AuditedModel, TimeStampedModel


def _uuid():
    return uuid.uuid4()


# ── المجالات الأربعة (من الاستمارة الرسمية) ─────────────────────────
OBSERVATION_DOMAINS = [
    ("planning", "التخطيط"),
    ("execution", "تنفيذ الدرس"),
    ("assessment", "التقويم"),
    ("management", "الإدارة الصفية وبيئة التعلم"),
]

# ── المقياس النوعي + وزن % لحساب النسبة الإجمالية ────────────────────
# "لم يُقَس" يُستثنى من الحساب (لا يدخل البسط ولا المقام).
RATING_CHOICES = [
    ("complete", "الأدلة مستكملة وفاعلة"),
    ("most", "تتوفر معظم الأدلة"),
    ("some", "تتوفر بعض الأدلة"),
    ("limited", "الأدلة غير متوفرة أو محدودة"),
    ("not_measured", "لم يتم قياسه"),
]
RATING_WEIGHTS = {"complete": 100, "most": 75, "some": 50, "limited": 25}

FOLLOW_UP_MODE = [("field", "ميدانيّة"), ("remote", "عن بُعد")]
FOLLOW_UP_SCOPE = [("partial", "جزئيّة"), ("full", "كلّيّة")]

OBSERVATION_STATUS = [
    ("draft", "مسودة"),
    ("submitted", "مُرسَلة للمعلّم"),
    ("acknowledged", "مُقَرّة من المعلّم"),
]


class ObservationCriterion(TimeStampedModel):
    """معيار أداء ضمن مجال — بيانات مرجعية ثابتة (مزروعة لكل مدرسة)."""

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="observation_criteria"
    )
    domain = models.CharField(max_length=20, choices=OBSERVATION_DOMAINS, verbose_name="المجال")
    text = models.TextField(verbose_name="معيار الأداء")
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "معيار ملاحظة صفّية"
        verbose_name_plural = "معايير الملاحظة الصفّية"
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "domain", "text"], name="uniq_observation_criterion"
            )
        ]

    def __str__(self):
        return f"{self.get_domain_display()} — {self.text[:50]}"


class ClassroomObservation(AuditedModel):
    """زيارة إشرافية واحدة على أداء معلّم في حصّة."""

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="classroom_observations"
    )
    teacher = models.ForeignKey(
        CustomUser, on_delete=models.PROTECT, related_name="observations_received",
        verbose_name="المعلّم",
    )
    observer = models.ForeignKey(
        CustomUser, on_delete=models.PROTECT, related_name="observations_made",
        verbose_name="الزائر",
    )
    subject = models.ForeignKey(
        "operations.Subject", on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="المادّة",
    )
    class_group = models.ForeignKey(
        "core.ClassGroup", on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="الصّف",
    )
    observation_date = models.DateField(default=timezone.localdate, verbose_name="التاريخ")
    period = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="الحصة")
    topic = models.CharField(max_length=200, blank=True, verbose_name="الموضوع")

    follow_up_mode = models.CharField(
        max_length=10, choices=FOLLOW_UP_MODE, blank=True, verbose_name="نوع المتابعة"
    )
    follow_up_scope = models.CharField(max_length=10, choices=FOLLOW_UP_SCOPE, blank=True)
    broadcast_note = models.CharField(max_length=200, blank=True, verbose_name="ملاحظات البث")
    general_notes = models.TextField(blank=True, verbose_name="ملاحظات وتوصيات عامّة")

    status = models.CharField(max_length=15, choices=OBSERVATION_STATUS, default="draft")
    score_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="النسبة الإجماليّة"
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    teacher_acknowledged_at = models.DateTimeField(null=True, blank=True)
    teacher_comment = models.TextField(blank=True, verbose_name="تعليق المعلّم")

    class Meta:
        verbose_name = "ملاحظة صفّية"
        verbose_name_plural = "الملاحظات الصفّية"
        ordering = ["-observation_date", "-created_at"]
        indexes = [
            models.Index(fields=["school", "teacher", "observation_date"]),
            models.Index(fields=["school", "status"]),
        ]

    def __str__(self):
        return f"إشراف {self.teacher.full_name} — {self.observation_date}"

    def compute_score_percent(self):
        """متوسط أوزان المعايير المُقيَّمة (باستثناء «لم يُقَس»). يُعيد None إن لا تقييم."""
        from decimal import Decimal

        rated = [
            RATING_WEIGHTS[s.rating]
            for s in self.scores.all()
            if s.rating in RATING_WEIGHTS
        ]
        if not rated:
            return None
        return (Decimal(sum(rated)) / Decimal(len(rated))).quantize(Decimal("0.01"))


class ObservationScore(TimeStampedModel):
    """تقييم معيار واحد ضمن زيارة + توصية."""

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    observation = models.ForeignKey(
        ClassroomObservation, on_delete=models.CASCADE, related_name="scores"
    )
    criterion = models.ForeignKey(
        ObservationCriterion, on_delete=models.PROTECT, related_name="scores"
    )
    rating = models.CharField(max_length=15, choices=RATING_CHOICES, blank=True)
    recommendation = models.TextField(blank=True, verbose_name="التوصية")

    class Meta:
        verbose_name = "تقييم معيار"
        verbose_name_plural = "تقييمات المعايير"
        ordering = ["criterion__order"]
        constraints = [
            models.UniqueConstraint(
                fields=["observation", "criterion"], name="uniq_observation_score"
            )
        ]

    def __str__(self):
        return f"{self.criterion} = {self.get_rating_display()}"
