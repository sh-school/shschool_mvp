"""
assessments/models.py
المرحلة 3 — نظام التقييمات والاختبارات

الهيكل الصحيح للتقييم في المدارس الحكومية القطرية (مواصفات وزارة التعليم):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
الفصل الأول  (40 درجة من أصل 100 سنوي)
  الباقة 3 — اختبار منتصف الفصل الأول : 6 درجات   (15% من ال100 = 37.5% من ال40)
  الباقة 1 — أعمال مستمرة ف1           : 2 درجتان  (5%  من ال100 = 12.5% من ال40)
  الباقة 4 — اختبار نهاية الفصل الأول  : 8 درجات   (20% من ال100 = 50%   من ال40)

الفصل الثاني (60 درجة من أصل 100 سنوي)
  الباقة 3 — اختبار منتصف الفصل الثاني : 9 درجات   (15% من ال100 = 25%    من ال60)
  الباقة 1 — أعمال مستمرة ف2           : 3 درجات   (5%  من ال100 = 8.33%  من ال60)
  الباقة 4 — اختبار نهاية العام         : 24 درجة   (40% من ال100 = 66.67% من ال60)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
المجموع السنوي = درجات الفصل الأول + درجات الفصل الثاني = 100
درجة النجاح السنوية = 60 من 100
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import ClassGroup, CustomUser, School
from operations.models import Subject

from .querysets import (
    AnnualResultQuerySet,
    AssessmentGradeQuerySet,
    SubjectResultQuerySet,
)


def _uuid():
    return uuid.uuid4()


# ─────────────────────────────────────────────────────────────
# 1. إعداد المادة للفصل الدراسي
# ─────────────────────────────────────────────────────────────


class SubjectClassSetup(models.Model):
    """ربط المادة بالفصل والمعلم المسؤول للعام الدراسي"""

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="subject_setups")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="class_setups")
    class_group = models.ForeignKey(
        ClassGroup, on_delete=models.CASCADE, related_name="subject_setups"
    )
    teacher = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name="subject_setups",
        verbose_name="المعلم المسؤول",
    )
    academic_year = models.CharField(max_length=9, default=settings.CURRENT_ACADEMIC_YEAR)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "إعداد مادة"
        verbose_name_plural = "إعدادات المواد"
        constraints = [
            models.UniqueConstraint(
                fields=["subject", "class_group", "academic_year"],
                condition=models.Q(is_active=True),
                name="unique_subject_class_year",
            )
        ]

    def __str__(self):
        return f"{self.subject.name_ar} | {self.class_group} | {self.teacher.full_name}"


# ─────────────────────────────────────────────────────────────
# 2. الباقات التقييمية
# ─────────────────────────────────────────────────────────────


class AssessmentPackage(models.Model):
    """
    باقة تقييمية داخل فصل دراسي.

    وزن الباقة (weight) = نسبة مئوية من مجموع الفصل (0–100).
    مجموع أوزان باقات الفصل الواحد يجب أن = 100.

    semester_max_grade = الدرجة القصوى للفصل من المجموع السنوي:
        الفصل الأول = 40
        الفصل الثاني = 60

    أي أن درجة الطالب الفعلية في الباقة:
        = (أداء الطالب % × weight%) × semester_max_grade / 100
    """

    PACKAGE_TYPE = [
        ("P1", "الباقة الأولى — أعمال مستمرة"),
        ("P2", "الباقة الثانية — اختبارات قصيرة"),
        ("P3", "الباقة الثالثة — اختبار منتصف الفصل"),
        ("P4", "الباقة الرابعة — اختبار نهائي"),
    ]
    SEMESTER = [
        ("S1", "الفصل الأول  (40 درجة)"),
        ("S2", "الفصل الثاني (60 درجة)"),
    ]

    # ─── الأوزان الصحيحة حسب مواصفات وزارة التعليم القطرية ───
    #
    # النسب هي أوزان داخل الفصل (تجمع إلى 100%)، محسوبة من:
    #   نقاط الباقة من المجموع الكلي (100) ÷ درجة الفصل القصوى × 100
    #
    # الفصل الأول (semester_max=40):
    #   P1 أعمال مستمرة   = 5%  من 100 → 12.5% من 40 →  2 درجة
    #   P2 اختبارات قصيرة = 0%  (غير مستخدم)
    #   P3 اختبار منتصف   = 15% من 100 → 37.5% من 40 →  6 درجات
    #   P4 اختبار نهائي   = 20% من 100 → 50%   من 40 →  8 درجات
    #   المجموع = 100% من 40 = 40 درجة ✓
    #
    # الفصل الثاني (semester_max=60):
    #   P1 أعمال مستمرة   = 5%  من 100 → 8.33%  من 60 →  3 درجات
    #   P2 اختبارات قصيرة = 0%  (غير مستخدم)
    #   P3 اختبار منتصف   = 15% من 100 → 25%    من 60 →  9 درجات
    #   P4 اختبار نهائي   = 40% من 100 → 66.67% من 60 → 24 درجة
    #   المجموع = 100% من 60 = 60 درجة ✓
    DEFAULT_WEIGHTS_S1 = {
        "P1": Decimal("12.50"),   # أعمال مستمرة → 2 من 40
        "P2": Decimal("0"),       # غير مستخدم في الفصل الأول
        "P3": Decimal("37.50"),   # اختبار منتصف الفصل الأول → 6 من 40
        "P4": Decimal("50"),      # اختبار نهاية الفصل الأول → 8 من 40
    }
    DEFAULT_WEIGHTS_S2 = {
        "P1": Decimal("8.33"),    # أعمال مستمرة → 3 من 60
        "P2": Decimal("0"),       # غير مستخدم
        "P3": Decimal("25"),      # اختبار منتصف الفصل الثاني → 9 من 60
        "P4": Decimal("66.67"),   # اختبار نهاية العام → 24 من 60
    }

    # درجة الفصل القصوى من المجموع السنوي
    SEMESTER_MAX = {
        "S1": Decimal("40"),
        "S2": Decimal("60"),
    }

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    setup = models.ForeignKey(SubjectClassSetup, on_delete=models.CASCADE, related_name="packages")
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="packages")
    package_type = models.CharField(max_length=2, choices=PACKAGE_TYPE, verbose_name="نوع الباقة")
    semester = models.CharField(max_length=2, choices=SEMESTER, default="S1")
    weight = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("25"),
        verbose_name="وزن الباقة من مجموع الفصل %",
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    semester_max_grade = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("40"),
        verbose_name="الدرجة القصوى للفصل من المجموع السنوي",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "باقة تقييم"
        verbose_name_plural = "باقات التقييم"
        constraints = [
            models.UniqueConstraint(
                fields=["setup", "package_type", "semester"],
                name="unique_package_per_setup_semester",
            )
        ]
        ordering = ["semester", "package_type"]

    def __str__(self):
        return (
            f"{self.get_package_type_display()} | "
            f"{self.setup.subject.name_ar} | {self.setup.class_group} | "
            f"{self.get_semester_display()}"
        )

    @property
    def effective_max_grade(self):
        """الدرجة الفعلية القصوى لهذه الباقة = وزنها × max الفصل / 100"""
        return (self.weight * self.semester_max_grade / Decimal("100")).quantize(Decimal("0.01"))

    @property
    def subject(self):
        return self.setup.subject

    @property
    def class_group(self):
        return self.setup.class_group


# ─────────────────────────────────────────────────────────────
# 3. التقييم الفعلي
# ─────────────────────────────────────────────────────────────


class Assessment(models.Model):
    """
    اختبار أو تقييم محدد داخل الباقة.
    الدرجة القصوى هنا هي الدرجة الخام (قد تكون 10 أو 20 أو 100).
    التحويل إلى الوزن النسبي يتم في GradeService.
    """

    ASSESSMENT_TYPE = [
        ("exam", "اختبار"),
        ("quiz", "اختبار قصير"),
        ("homework", "واجب"),
        ("project", "مشروع"),
        ("classwork", "عمل صفي"),
        ("oral", "شفهي"),
        ("practical", "عملي"),
        ("participation", "مشاركة صفية"),
    ]
    STATUS = [
        ("draft", "مسودة"),
        ("published", "منشور"),
        ("graded", "مصحَّح"),
        ("closed", "مغلق"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    package = models.ForeignKey(
        AssessmentPackage, on_delete=models.CASCADE, related_name="assessments"
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="assessments")
    title = models.CharField(max_length=200, verbose_name="عنوان التقييم")
    assessment_type = models.CharField(max_length=15, choices=ASSESSMENT_TYPE, default="exam")
    date = models.DateField(verbose_name="تاريخ التقييم", null=True, blank=True)
    max_grade = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("10"), verbose_name="الدرجة القصوى الخام"
    )
    weight_in_package = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("100"),
        verbose_name="وزنه داخل الباقة %",
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    status = models.CharField(max_length=10, choices=STATUS, default="draft", db_index=True)
    description = models.TextField(blank=True, verbose_name="وصف / تعليمات")
    created_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, related_name="created_assessments"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "تقييم"
        verbose_name_plural = "التقييمات"
        ordering = ["date", "package__package_type"]

    def __str__(self):
        return f"{self.title} | {self.package.setup.subject.name_ar} | {self.package.class_group}"

    @property
    def class_group(self):
        return self.package.setup.class_group

    @property
    def subject(self):
        return self.package.setup.subject


# ─────────────────────────────────────────────────────────────
# 4. درجات الطلاب
# ─────────────────────────────────────────────────────────────


class StudentAssessmentGrade(models.Model):
    """درجة طالب في تقييم خام"""

    objects = AssessmentGradeQuerySet.as_manager()

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="grades")
    student = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="assessment_grades"
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="student_grades")
    grade = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="الدرجة الخام",
        validators=[MinValueValidator(0)],
    )
    is_absent = models.BooleanField(default=False, verbose_name="غائب")
    is_excused = models.BooleanField(default=False, verbose_name="معذور")
    notes = models.CharField(max_length=200, blank=True, verbose_name="ملاحظة")
    entered_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, related_name="entered_grades"
    )
    entered_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "درجة طالب"
        verbose_name_plural = "درجات الطلاب"
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "student"], name="unique_grade_per_student_assessment"
            )
        ]
        indexes = [
            models.Index(fields=["student", "school"]),
            models.Index(fields=["assessment", "school"]),
        ]

    def __str__(self):
        g = self.grade if self.grade is not None else "—"
        return f"{self.student.full_name} | {self.assessment.title} | {g}"

    @property
    def grade_pct(self):
        """تحويل الدرجة الخام إلى نسبة % من الـ max"""
        if self.grade is None or self.assessment.max_grade == 0:
            return None
        return round(float(self.grade) / float(self.assessment.max_grade) * 100, 2)

    @property
    def status_label(self):
        if self.is_absent:
            return "غائب"
        if self.is_excused:
            return "معذور"
        if self.grade is None:
            return "لم تُدخَل"
        return str(self.grade)


# ─────────────────────────────────────────────────────────────
# 5. نتيجة الطالب في المادة — لكل فصل
# ─────────────────────────────────────────────────────────────


class StudentSubjectResult(models.Model):
    """
    درجة الطالب في مادة لفصل واحد — مخزونة من حساب الباقات.

    total = الدرجة الفعلية من مجموع الفصل:
        الفصل الأول: total ∈ [0, 40]
        الفصل الثاني: total ∈ [0, 60]

    لا يوجد نجاح/رسوب هنا — النجاح يُحسب في AnnualSubjectResult.
    """

    objects = SubjectResultQuerySet.as_manager()

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    student = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="subject_results"
    )
    setup = models.ForeignKey(
        SubjectClassSetup, on_delete=models.CASCADE, related_name="student_results"
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="subject_results")
    semester = models.CharField(max_length=2, choices=AssessmentPackage.SEMESTER, default="S1")

    # درجة كل باقة من مجموع الفصل (ليس نسبة مئوية)
    p1_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="درجة الباقة 1"
    )
    p2_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="درجة الباقة 2"
    )
    p3_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="درجة الباقة 3"
    )
    p4_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="درجة الباقة 4"
    )
    total = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="مجموع الفصل"
    )
    semester_max = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("40"), verbose_name="الدرجة القصوى للفصل"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "نتيجة فصل"
        verbose_name_plural = "نتائج الفصول"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "setup", "semester"],
                name="unique_result_per_student_setup_semester",
            )
        ]
        indexes = [
            models.Index(fields=["student", "school", "semester"]),
            models.Index(fields=["setup", "semester"]),
        ]

    def __str__(self):
        return (
            f"{self.student.full_name} | {self.setup.subject.name_ar} | "
            f"{self.get_semester_display()} | {self.total or '—'}/{self.semester_max}"
        )

    @property
    def subject(self):
        return self.setup.subject

    @property
    def class_group(self):
        return self.setup.class_group

    @property
    def total_pct(self):
        """النسبة المئوية من مجموع الفصل"""
        if self.total is None or self.semester_max == 0:
            return None
        return round(float(self.total) / float(self.semester_max) * 100, 1)


# ─────────────────────────────────────────────────────────────
# 6. النتيجة السنوية للطالب في المادة ← الجديد
# ─────────────────────────────────────────────────────────────


class AnnualSubjectResult(models.Model):
    """
    النتيجة السنوية النهائية للطالب في مادة.

    annual_total = s1_total + s2_total
    النجاح: annual_total >= 60 من 100
    """

    objects = AnnualResultQuerySet.as_manager()

    STATUS = [
        ("pass", "ناجح"),
        ("fail", "راسب"),
        ("incomplete", "غير مكتمل"),
        ("second_round", "دور ثانٍ"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="annual_results")
    setup = models.ForeignKey(
        SubjectClassSetup, on_delete=models.CASCADE, related_name="annual_results"
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="annual_results")
    academic_year = models.CharField(max_length=9, default=settings.CURRENT_ACADEMIC_YEAR)

    # مجاميع الفصلين (من نتائجهما المحسوبة)
    s1_total = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="مجموع الفصل الأول (من 40)",
    )
    s2_total = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="مجموع الفصل الثاني (من 60)",
    )
    annual_total = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="المجموع السنوي (من 100)",
    )
    pass_grade = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("60"), verbose_name="درجة النجاح"
    )
    status = models.CharField(max_length=12, choices=STATUS, default="incomplete", db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "نتيجة سنوية"
        verbose_name_plural = "النتائج السنوية"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "setup", "academic_year"], name="unique_annual_result"
            )
        ]
        indexes = [
            models.Index(fields=["student", "school", "academic_year"]),
            models.Index(fields=["status", "school", "academic_year"]),
        ]

    def __str__(self):
        return (
            f"{self.student.full_name} | {self.setup.subject.name_ar} | "
            f"{self.academic_year} | {self.annual_total or '—'}/100"
        )

    @property
    def subject(self):
        return self.setup.subject

    @property
    def class_group(self):
        return self.setup.class_group

    @property
    def letter_grade(self):
        if self.annual_total is None:
            return "—"
        t = float(self.annual_total)
        if t >= 95:
            return "A+"
        if t >= 90:
            return "A"
        if t >= 85:
            return "B+"
        if t >= 80:
            return "B"
        if t >= 75:
            return "C+"
        if t >= 70:
            return "C"
        if t >= 65:
            return "D+"
        if t >= 60:
            return "D"
        return "F"

    @property
    def grade_color_css(self):
        if self.annual_total is None:
            return "text-gray-400"
        t = float(self.annual_total)
        if t >= 80:
            return "text-green-700"
        if t >= 65:
            return "text-blue-700"
        if t >= 60:
            return "text-amber-600"
        return "text-red-600"
