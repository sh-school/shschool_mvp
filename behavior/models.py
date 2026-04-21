"""
behavior/models.py
نماذج السلوك الطلابي — v6 (لائحة مدرسة الشحانية)
✅ ViolationCategory: 40 مخالفة رسمية × 4 درجات
✅ BehaviorInfraction: حقول الإحالة الأمنية + التشهير الرقمي + الإجراء التصاعدي
✅ BehaviorPointRecovery: استعادة النقاط (التعزيز الإيجابي)
"""

import uuid

from django.db import models

from .constants import (
    DEGREE_CHOICES,
    ESCALATION_STEPS,
    SECURITY_AGENCIES,
    SOCIAL_MEDIA_PLATFORMS,
    VIOLATIONS_2025,
)
from .querysets import InfractionQuerySet, RecoveryQuerySet


def _uuid():
    return uuid.uuid4()


# ─────────────────────────────────────────────────────────────────
# ViolationCategory — لائحة المخالفات الرسمية 2025-2026
# ─────────────────────────────────────────────────────────────────
class ViolationCategory(models.Model):
    """
    فئة مخالفة سلوكية وفق لائحة مدرسة الشحانية (SOS-20260420-1E01)
    4 درجات × 40 مخالفة — يُحقن بأمر: python manage.py seed_violations_2025
    """

    # ── keep old ABCD for backward compat ──
    CATEGORY_CHOICES = [
        ("A", "الفئة A — خفيفة"),
        ("B", "الفئة B — متوسطة"),
        ("C", "الفئة C — جسيمة"),
        ("D", "الفئة D — حرجة"),
    ]
    DEFAULT_ACTIONS = {
        "A": "تنبيه شفهي / كتابي",
        "B": "إنذار أول + خطة علاجية",
        "C": "إنذار ثانٍ + لجنة سلوك",
        "D": "فصل مؤقت / نهائي + إحالة رسمية",
    }

    TAG_CHOICES = [
        ("tech", "🔷 تقني"),
        ("safety", "🛡️ حماية"),
        ("law", "⚖️ قانوني"),
        ("national", "🇶🇦 وطني"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)

    # ── الدرجة الرسمية (1-4) — الحقل الرئيسي الجديد ──
    degree = models.PositiveSmallIntegerField(
        choices=DEGREE_CHOICES,
        default=1,
        db_index=True,
        verbose_name="الدرجة الرسمية (1-4)",
    )

    # ── الحقول الأصلية (محدّثة) ──
    category = models.CharField(
        max_length=1,
        choices=CATEGORY_CHOICES,
        blank=True,
        default="",
        verbose_name="الفئة القديمة (ABCD)",
        help_text="⚠ حقل قديم — يُستخدم فقط للمخالفات المحقونة قبل 2025",
    )
    code = models.CharField(
        max_length=10,
        unique=True,
        verbose_name="الرمز",
        help_text="مثال: 1-01, 2-05, 3-07, 4-13",
    )
    name_ar = models.CharField(max_length=300, verbose_name="اسم المخالفة")
    default_action = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="الإجراء الافتراضي",
    )
    points = models.PositiveSmallIntegerField(default=5, verbose_name="النقاط المخصومة")
    is_active = models.BooleanField(default=True)

    # ── حقول جديدة 2025 ──
    tags = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="تصنيفات",
        help_text="فاصل: tech,safety,law,national",
    )
    requires_security_referral = models.BooleanField(
        default=False,
        verbose_name="يتطلب إحالة أمنية",
    )
    requires_parent_summon = models.BooleanField(
        default=False,
        verbose_name="يتطلب استدعاء ولي أمر فوري",
    )

    class Meta:
        verbose_name = "فئة مخالفة سلوكية"
        verbose_name_plural = "فئات المخالفات السلوكية (2025)"
        ordering = ["degree", "code"]

    def __str__(self):
        return f"[{self.code}] {self.name_ar}"

    def save(self, *args, **kwargs):
        if not self.default_action and self.category:
            self.default_action = self.DEFAULT_ACTIONS.get(self.category, "")
        # الدرجة الرابعة تتطلب إحالة أمنية دائماً
        if self.degree == 4:
            self.requires_security_referral = True
            self.requires_parent_summon = True
        elif self.degree == 3:
            self.requires_parent_summon = True
        super().save(*args, **kwargs)

    @property
    def tag_list(self):
        """إرجاع التصنيفات كقائمة"""
        return [t.strip() for t in self.tags.split(",") if t.strip()]

    @property
    def is_tech(self):
        return "tech" in self.tags

    @property
    def is_new_2025(self):
        """هل هي مخالفة جديدة في إصدار 2025؟"""
        return "tech" in self.tags and self.degree >= 3

    def get_escalation_steps(self):
        """إرجاع خطوات الإجراءات التصاعدية لدرجة هذه المخالفة"""
        return ESCALATION_STEPS.get(self.degree, [])

    # ── الحقن القديم للتوافق ──
    @classmethod
    def seed_abcd(cls):
        """تغذية لائحة ABCD القديمة (20 مخالفة) — deprecated"""
        violations = [
            ("A", "A1", "مخالفة الزي المدرسي", 3, 1),
            ("A", "A2", "التأخر عن الدوام", 3, 1),
            ("A", "A3", "نسيان الأدوات والكتب", 2, 1),
            ("A", "A4", "إزعاج وإشغال الفصل", 4, 1),
            ("A", "A5", "مخالفة تعليمات الأنشطة", 3, 1),
            ("B", "B1", "غياب غير مبرر", 8, 2),
            ("B", "B2", "إساءة لفظية لزميل", 10, 2),
            ("B", "B3", "تخريب بسيط للممتلكات", 10, 2),
            ("B", "B4", "مخالفة قواعد السلامة", 8, 2),
            ("B", "B5", "مخالفة سياسة الأجهزة التقنية", 8, 2),
            ("C", "C1", "تنمر لفظي متكرر", 15, 3),
            ("C", "C2", "اعتداء جسدي بسيط", 15, 3),
            ("C", "C3", "تخريب جسيم للممتلكات", 15, 3),
            ("C", "C4", "مخالفة أمن السلامة المدرسية", 15, 3),
            ("C", "C5", "مخالفة أنظمة الاختبارات", 20, 3),
            ("D", "D1", "تنمر جسدي خطير", 25, 4),
            ("D", "D2", "اعتداء على موظف", 25, 4),
            ("D", "D3", "إحضار أدوات خطرة", 25, 4),
            ("D", "D4", "غش مؤكد في الاختبارات", 20, 4),
            ("D", "D5", "انتهاك سياسة حماية الطلبة", 25, 4),
        ]
        created = 0
        for cat, code, name, pts, deg in violations:
            obj, made = cls.objects.get_or_create(
                code=code,
                defaults={
                    "category": cat,
                    "name_ar": name,
                    "points": pts,
                    "degree": deg,
                },
            )
            if made:
                created += 1
        return created

    @classmethod
    def seed_2025(cls):
        """حقن 40 مخالفة رسمية وفق لائحة مدرسة الشحانية (SOS-20260420-1E01)"""
        created = 0
        for degree, code, name, pts, tag_list in VIOLATIONS_2025:
            obj, made = cls.objects.get_or_create(
                code=code,
                defaults={
                    "degree": degree,
                    "name_ar": name,
                    "points": pts,
                    "tags": ",".join(tag_list),
                    "requires_security_referral": degree == 4,
                    "requires_parent_summon": degree >= 3,
                },
            )
            if made:
                created += 1
        return created


# ─────────────────────────────────────────────────────────────────
# BehaviorInfraction — مخالفة سلوكية مسجّلة
# ─────────────────────────────────────────────────────────────────
class BehaviorInfraction(models.Model):
    """مخالفة سلوكية — وفق لائحة وزارة التربية القطرية 2025-2026"""

    LEVELS = [
        (1, "الدرجة الأولى (بسيطة)"),
        (2, "الدرجة الثانية (متوسطة)"),
        (3, "الدرجة الثالثة (خطيرة)"),
        (4, "الدرجة الرابعة (جسيمة)"),
    ]

    ESCALATION_STEP_CHOICES = [
        (0, "لم يُتخذ إجراء بعد"),
        (1, "الإجراء الأول"),
        (2, "الإجراء الثاني"),
        (3, "الإجراء الثالث"),
        (4, "الإجراء الرابع"),
    ]

    objects = InfractionQuerySet.as_manager()

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey("core.School", on_delete=models.CASCADE)
    student = models.ForeignKey(
        "core.CustomUser",
        on_delete=models.PROTECT,
        related_name="behavior_infractions",
    )
    reported_by = models.ForeignKey(
        "core.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        related_name="reported_infractions",
    )

    # ── فئة المخالفة ──
    violation_category = models.ForeignKey(
        ViolationCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="فئة المخالفة",
        related_name="infractions",
    )

    # ── التواريخ ──
    date = models.DateField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    # ── الدرجة والوصف ──
    level = models.PositiveSmallIntegerField(
        choices=LEVELS,
        default=1,
        db_index=True,
    )
    description = models.TextField(
        verbose_name="وصف المخالفة",
        max_length=2000,
    )
    action_taken = models.TextField(
        blank=True,
        verbose_name="الإجراء المتخذ",
        max_length=2000,
    )

    # ── REQ-SH-001 (Client #001 — Shahaniya School, MTG-007) ──
    # Structured disciplinary action dropdown + conditional violation description.
    DISCIPLINARY_ACTION_CHOICES = [
        ("verbal_warning", "تنبيه شفهي"),
        ("written_pledge", "تعهد خطي"),
        ("incident_report", "محضر لإثبات المخالفة"),
        ("parent_pledge", "تعهد خطي لولي الأمر"),
        ("social_specialist_referral", "تحويل للأخصائي الاجتماعي"),
        ("parent_summons", "استدعاء ولي الأمر"),
    ]
    disciplinary_action_type = models.CharField(
        max_length=50,
        choices=DISCIPLINARY_ACTION_CHOICES,
        blank=True,
        default="",
        verbose_name="الإجراء التأديبي",
        help_text="الإجراء التأديبي الرسمي وفق لائحة المدرسة",
    )
    violation_description = models.TextField(
        blank=True,
        default="",
        max_length=2000,
        verbose_name="وصف المخالفة (محضر)",
        help_text="مطلوب فقط عند اختيار 'محضر لإثبات المخالفة' (20-2000 حرف)",
    )

    points_deducted = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="النقاط المخصومة",
    )

    # ── خطوة الإجراء التصاعدي الحالية ──
    escalation_step = models.PositiveSmallIntegerField(
        choices=ESCALATION_STEP_CHOICES,
        default=0,
        verbose_name="خطوة الإجراء التصاعدي",
        help_text="أي خطوة من الإجراءات التصاعدية تم تنفيذها",
    )

    # ── حقول التشهير الرقمي (الدرجة 3 — مخالفات تقنية) ──
    social_media_platform = models.CharField(
        max_length=20,
        choices=SOCIAL_MEDIA_PLATFORMS,
        blank=True,
        default="",
        verbose_name="منصة التواصل الاجتماعي",
        help_text="عند تسجيل مخالفة تشهير أو تصوير رقمي",
    )
    digital_evidence_notes = models.TextField(
        blank=True,
        default="",
        verbose_name="ملاحظات الأدلة الرقمية",
        help_text="وصف الأدلة الرقمية (روابط، لقطات شاشة، إلخ)",
        max_length=1000,
    )

    # ── حقول الإحالة الأمنية (الدرجة 4) ──
    security_referral_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="تاريخ الإحالة الأمنية",
    )
    security_agency = models.CharField(
        max_length=30,
        choices=SECURITY_AGENCIES,
        blank=True,
        default="",
        verbose_name="الجهة الأمنية المُحالة إليها",
    )
    security_reference_number = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="رقم المرجع الأمني",
    )
    security_notes = models.TextField(
        blank=True,
        default="",
        verbose_name="ملاحظات الإحالة الأمنية",
        max_length=1000,
    )

    # ── استدعاء ولي الأمر ──
    parent_summoned = models.BooleanField(
        default=False,
        verbose_name="تم استدعاء ولي الأمر",
    )
    parent_summon_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="تاريخ استدعاء ولي الأمر",
    )
    parent_undertaking_signed = models.BooleanField(
        default=False,
        verbose_name="تم توقيع تعهد ولي الأمر",
    )

    # ── إيقاف الطالب ──
    suspension_days = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="أيام الإيقاف",
    )
    suspension_type = models.CharField(
        max_length=20,
        choices=[
            ("", "—"),
            ("internal", "إيقاف داخل المدرسة"),
            ("external", "إيقاف خارج المدرسة"),
        ],
        blank=True,
        default="",
        verbose_name="نوع الإيقاف",
    )

    # ── الحالة ──
    is_resolved = models.BooleanField(default=False)

    class Meta:
        verbose_name = "مخالفة سلوكية"
        verbose_name_plural = "المخالفات السلوكية"
        ordering = ["-date", "-created_at"]
        db_table = "core_behaviorinfraction"
        indexes = [
            models.Index(fields=["school", "date"], name="idx_infraction_school_date"),
            models.Index(
                fields=["school", "level", "is_resolved"], name="idx_infraction_level_resolved"
            ),
        ]

    def __str__(self):
        cat = f" [{self.violation_category.code}]" if self.violation_category else ""
        return f"{self.student.full_name}{cat} - {self.get_level_display()}"

    def save(self, *args, **kwargs):
        # نظام النقاط ملغى — لا نملأ points_deducted تلقائياً
        # تعيين الدرجة تلقائياً من فئة المخالفة
        if self.violation_category and self.violation_category.degree:
            self.level = self.violation_category.degree
        super().save(*args, **kwargs)

    @property
    def requires_security_referral(self):
        """هل تتطلب هذه المخالفة إحالة أمنية؟"""
        if self.violation_category:
            return self.violation_category.requires_security_referral
        return self.level == 4

    @property
    def requires_parent_summon(self):
        """هل تتطلب استدعاء ولي أمر فوري؟"""
        if self.violation_category:
            return self.violation_category.requires_parent_summon
        return self.level >= 3

    def get_escalation_steps(self):
        """إرجاع الإجراءات التصاعدية المتاحة لهذه المخالفة"""
        return ESCALATION_STEPS.get(self.level, [])

    def get_current_step_text(self):
        """إرجاع نص خطوة الإجراء الحالية"""
        steps = self.get_escalation_steps()
        for step_num, text in steps:
            if step_num == self.escalation_step:
                return text
        return ""

    def get_next_step(self):
        """إرجاع الخطوة التالية (إن وُجدت)"""
        steps = self.get_escalation_steps()
        for step_num, text in steps:
            if step_num > self.escalation_step:
                return (step_num, text)
        return None


# ─────────────────────────────────────────────────────────────────
# BehaviorPointRecovery — استعادة النقاط (التعزيز الإيجابي)
# ─────────────────────────────────────────────────────────────────
class BehaviorPointRecovery(models.Model):
    """استعادة نقاط السلوك — التعزيز الإيجابي"""

    objects = RecoveryQuerySet.as_manager()

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    infraction = models.OneToOneField(
        BehaviorInfraction,
        on_delete=models.CASCADE,
        related_name="recovery",
    )
    reason = models.TextField(verbose_name="سبب استعادة النقاط (سلوك إيجابي)")
    points_restored = models.PositiveIntegerField(default=0)
    approved_by = models.ForeignKey(
        "core.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
    )
    date = models.DateField(auto_now_add=True)

    class Meta:
        verbose_name = "استعادة نقاط"
        verbose_name_plural = "استعادة النقاط"
        db_table = "core_behaviorpointrecovery"

    def __str__(self):
        return f"Recovery: {self.infraction.student.full_name} (+{self.points_restored})"
