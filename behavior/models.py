"""
behavior/models.py
نماذج السلوك الطلابي — مُحدَّث v5
✅ إضافة ViolationCategory (لائحة ABCD من Ct.zip)
✅ ربط BehaviorInfraction بـ ViolationCategory
db_table مضبوط صراحةً لإبقاء نفس الجداول في قاعدة البيانات
"""
import uuid
from django.db import models


def _uuid():
    return uuid.uuid4()


class ViolationCategory(models.Model):
    """
    لائحة المخالفات السلوكية ABCD — مستوردة من Ct.zip
    A=خفيفة | B=متوسطة | C=جسيمة | D=حرجة
    """
    CATEGORY_CHOICES = [
        ('A', 'الفئة A — خفيفة'),
        ('B', 'الفئة B — متوسطة'),
        ('C', 'الفئة C — جسيمة'),
        ('D', 'الفئة D — حرجة'),
    ]
    DEFAULT_ACTIONS = {
        'A': 'تنبيه شفهي / كتابي',
        'B': 'إنذار أول + خطة علاجية',
        'C': 'إنذار ثانٍ + لجنة سلوك',
        'D': 'فصل مؤقت / نهائي + إحالة رسمية',
    }

    id             = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    category       = models.CharField(max_length=1, choices=CATEGORY_CHOICES, verbose_name="الفئة")
    code           = models.CharField(max_length=3, unique=True, verbose_name="الرمز (A1-D5)")
    name_ar        = models.CharField(max_length=200, verbose_name="اسم المخالفة")
    default_action = models.CharField(max_length=300, blank=True, verbose_name="الإجراء الافتراضي")
    points         = models.PositiveSmallIntegerField(default=5, verbose_name="النقاط المخصومة")
    is_active      = models.BooleanField(default=True)

    class Meta:
        verbose_name        = "فئة مخالفة سلوكية"
        verbose_name_plural = "فئات المخالفات السلوكية (ABCD)"
        ordering            = ['category', 'code']

    def __str__(self):
        return f"[{self.code}] {self.name_ar}"

    def save(self, *args, **kwargs):
        if not self.default_action and self.category:
            self.default_action = self.DEFAULT_ACTIONS.get(self.category, '')
        super().save(*args, **kwargs)

    @classmethod
    def seed_abcd(cls):
        """تغذية لائحة ABCD الكاملة (20 مخالفة) من Ct.zip"""
        violations = [
            # A — خفيفة
            ('A', 'A1', 'مخالفة الزي المدرسي', 3),
            ('A', 'A2', 'التأخر عن الدوام', 3),
            ('A', 'A3', 'نسيان الأدوات والكتب', 2),
            ('A', 'A4', 'إزعاج وإشغال الفصل', 4),
            ('A', 'A5', 'مخالفة تعليمات الأنشطة', 3),
            # B — متوسطة
            ('B', 'B1', 'غياب غير مبرر', 8),
            ('B', 'B2', 'إساءة لفظية لزميل', 10),
            ('B', 'B3', 'تخريب بسيط للممتلكات', 10),
            ('B', 'B4', 'مخالفة قواعد السلامة', 8),
            ('B', 'B5', 'مخالفة سياسة الأجهزة التقنية', 8),
            # C — جسيمة
            ('C', 'C1', 'تنمر لفظي متكرر', 15),
            ('C', 'C2', 'اعتداء جسدي بسيط', 15),
            ('C', 'C3', 'تخريب جسيم للممتلكات', 15),
            ('C', 'C4', 'مخالفة أمن السلامة المدرسية', 15),
            ('C', 'C5', 'مخالفة أنظمة الاختبارات', 20),
            # D — حرجة
            ('D', 'D1', 'تنمر جسدي خطير', 25),
            ('D', 'D2', 'اعتداء على موظف', 25),
            ('D', 'D3', 'إحضار أدوات خطرة', 25),
            ('D', 'D4', 'غش مؤكد في الاختبارات', 20),
            ('D', 'D5', 'انتهاك سياسة حماية الطلبة', 25),
        ]
        created = 0
        for cat, code, name, pts in violations:
            obj, made = cls.objects.get_or_create(
                code=code,
                defaults={'category': cat, 'name_ar': name, 'points': pts}
            )
            if made:
                created += 1
        return created


class BehaviorInfraction(models.Model):
    """مخالفة سلوكية — 4 درجات وفق لائحة وزارة التعليم القطرية"""
    LEVELS = [
        (1, 'الدرجة الأولى (بسيطة)'),
        (2, 'الدرجة الثانية (متوسطة)'),
        (3, 'الدرجة الثالثة (جسيمة)'),
        (4, 'الدرجة الرابعة (شديدة الخطورة)'),
    ]
    id              = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school          = models.ForeignKey('core.School', on_delete=models.CASCADE)
    student         = models.ForeignKey(
        'core.CustomUser', on_delete=models.CASCADE, related_name="behavior_infractions"
    )
    reported_by     = models.ForeignKey(
        'core.CustomUser', on_delete=models.SET_NULL, null=True, related_name="reported_infractions"
    )
    # ✅ جديد v5: ربط بلائحة ABCD
    violation_category = models.ForeignKey(
        ViolationCategory, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="فئة المخالفة (ABCD)",
        related_name="infractions"
    )
    date            = models.DateField(auto_now_add=True)
    created_at      = models.DateTimeField(auto_now_add=True, null=True)
    level           = models.PositiveSmallIntegerField(choices=LEVELS, default=1)
    description     = models.TextField(verbose_name="وصف المخالفة", max_length=2000)
    action_taken    = models.TextField(blank=True, verbose_name="الإجراء المتخذ", max_length=2000)
    points_deducted = models.PositiveSmallIntegerField(default=0, verbose_name="النقاط المخصومة")
    is_resolved     = models.BooleanField(default=False)

    class Meta:
        verbose_name        = "مخالفة سلوكية"
        verbose_name_plural = "المخالفات السلوكية"
        ordering            = ['-date', '-created_at']
        db_table            = "core_behaviorinfraction"

    def __str__(self):
        cat = f" [{self.violation_category.code}]" if self.violation_category else ""
        return f"{self.student.full_name}{cat} - {self.get_level_display()}"

    def save(self, *args, **kwargs):
        """تعيين النقاط تلقائياً من فئة المخالفة"""
        if self.violation_category and not self.points_deducted:
            self.points_deducted = self.violation_category.points
        super().save(*args, **kwargs)


class BehaviorPointRecovery(models.Model):
    """استعادة نقاط السلوك — التعزيز الإيجابي"""
    id              = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    infraction      = models.OneToOneField(
        BehaviorInfraction, on_delete=models.CASCADE, related_name="recovery"
    )
    reason          = models.TextField(verbose_name="سبب استعادة النقاط (سلوك إيجابي)")
    points_restored = models.PositiveIntegerField(default=0)
    approved_by     = models.ForeignKey(
        'core.CustomUser', on_delete=models.SET_NULL, null=True
    )
    date            = models.DateField(auto_now_add=True)

    class Meta:
        verbose_name        = "استعادة نقاط"
        verbose_name_plural = "استعادة النقاط"
        db_table            = "core_behaviorpointrecovery"   # يبقي نفس الجدول الموجود

    def __str__(self):
        return f"Recovery: {self.infraction.student.full_name} (+{self.points_restored})"
