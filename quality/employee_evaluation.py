"""
quality/employee_evaluation.py
Phase 6 — تقييم أداء الموظفين
بموجب: القرار الأميري 9/2016 م.11 + قانون تنظيم المدارس 9/2017
معايير QNSA 2024: المعيار 1 (القيادة الإدارية) + المعيار 4 (إدارة الموارد)

نظام التقييم: 4 مستويات (ممتاز، جيد جداً، جيد، يحتاج تطوير)
الدورية: مرتين سنوياً (نهاية الفصل الأول + نهاية العام)
"""

from django.conf import settings

import uuid

from django.db import models
from django.utils import timezone

from core.models import CustomUser, School


def _uuid():
    return uuid.uuid4()


class EmployeeEvaluation(models.Model):
    """
    تقييم الأداء الوظيفي — القرار الأميري 9/2016 م.11
    مطلوب لجميع الموظفين في المدارس الحكومية
    """

    PERIODS = [
        ("S1", "نهاية الفصل الأول"),
        ("S2", "نهاية العام الدراسي"),
    ]
    RATINGS = [
        ("excellent", "ممتاز (90–100)"),
        ("very_good", "جيد جداً (75–89)"),
        ("good", "جيد (60–74)"),
        ("needs_dev", "يحتاج تطوير (أقل من 60)"),
    ]
    STATUS = [
        ("draft", "مسودة"),
        ("submitted", "مُقدَّم"),
        ("approved", "مُعتمد"),
        ("acknowledged", "مُستلم من الموظف"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="evaluations")
    employee = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="evaluations", verbose_name="الموظف"
    )
    evaluator = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="evaluations_given",
        verbose_name="المقيِّم",
    )
    academic_year = models.CharField(max_length=9, default=settings.CURRENT_ACADEMIC_YEAR)
    period = models.CharField(max_length=2, choices=PERIODS, verbose_name="الفترة")
    status = models.CharField(max_length=15, choices=STATUS, default="draft")

    # ── محاور التقييم ─────────────────────────────────────────
    # كل محور من 0–25 درجة = مجموع 100
    axis_professional = models.PositiveSmallIntegerField(
        default=0, verbose_name="الكفاءة المهنية (25)"
    )
    axis_commitment = models.PositiveSmallIntegerField(
        default=0, verbose_name="الالتزام والمسؤولية (25)"
    )
    axis_teamwork = models.PositiveSmallIntegerField(
        default=0, verbose_name="العمل الجماعي والتواصل (25)"
    )
    axis_development = models.PositiveSmallIntegerField(
        default=0, verbose_name="التطوير المهني والمبادرة (25)"
    )

    total_score = models.PositiveSmallIntegerField(default=0, verbose_name="المجموع الكلي")
    rating = models.CharField(max_length=15, choices=RATINGS, blank=True)

    strengths = models.TextField(blank=True, verbose_name="نقاط القوة")
    improvements = models.TextField(blank=True, verbose_name="مجالات التطوير")
    goals_next = models.TextField(blank=True, verbose_name="أهداف الفترة القادمة")

    employee_comment = models.TextField(blank=True, verbose_name="تعليق الموظف")
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "تقييم موظف"
        verbose_name_plural = "تقييمات الموظفين"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "employee", "academic_year", "period"],
                name="unique_eval_per_period",
            )
        ]

    def __str__(self):
        return f"{self.employee.full_name} | {self.get_period_display()} | {self.academic_year}"

    def calculate_total(self):
        """حساب المجموع وتحديد التقدير"""
        self.total_score = (
            self.axis_professional
            + self.axis_commitment
            + self.axis_teamwork
            + self.axis_development
        )
        if self.total_score >= 90:
            self.rating = "excellent"
        elif self.total_score >= 75:
            self.rating = "very_good"
        elif self.total_score >= 60:
            self.rating = "good"
        else:
            self.rating = "needs_dev"

    def save(self, *args, **kwargs):
        self.calculate_total()
        super().save(*args, **kwargs)

    def acknowledge(self):
        """الموظف يُقرّ باستلام التقييم"""
        self.status = "acknowledged"
        self.acknowledged_at = timezone.now()
        self.save(update_fields=["status", "acknowledged_at"])


class EvaluationCycle(models.Model):
    """
    دورة التقييم السنوية — تُدار بواسطة مدير المدرسة
    تضمن تقييم 100% من الموظفين كما يشترط القرار الأميري 9/2016
    """

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="eval_cycles")
    academic_year = models.CharField(max_length=9, default=settings.CURRENT_ACADEMIC_YEAR)
    period = models.CharField(max_length=2, choices=EmployeeEvaluation.PERIODS)
    deadline = models.DateField(verbose_name="الموعد النهائي للتقييم")
    is_closed = models.BooleanField(default=False)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "دورة تقييم"
        verbose_name_plural = "دورات التقييم"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "academic_year", "period"],
                name="unique_eval_cycle",
            )
        ]

    def __str__(self):
        return f"{self.school.code} | {self.get_period_display()} | {self.academic_year}"

    @property
    def completion_rate(self):
        """نسبة إكمال التقييمات في هذه الدورة"""
        from core.models import Membership

        total_staff = Membership.objects.filter(
            school=self.school,
            is_active=True,
            role__name__in=[
                "teacher",
                "coordinator",
                "specialist",
                "nurse",
                "librarian",
                "bus_supervisor",
                "admin",
                "vice_admin",
                "vice_academic",
            ],
        ).count()
        evaluated = EmployeeEvaluation.objects.filter(
            school=self.school,
            academic_year=self.academic_year,
            period=self.period,
            status__in=["submitted", "approved", "acknowledged"],
        ).count()
        if total_staff == 0:
            return 0
        return round(evaluated / total_staff * 100)
