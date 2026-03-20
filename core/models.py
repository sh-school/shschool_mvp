import uuid
from django.db import models
from django.conf import settings
import base64, os
try:
    from cryptography.fernet import Fernet
    _FERNET_AVAILABLE = True
except ImportError:
    _FERNET_AVAILABLE = False


def _get_fernet():
    if not _FERNET_AVAILABLE:
        return None
    key = getattr(settings, 'FERNET_KEY', None)
    if not key:
        if getattr(settings, 'DEBUG', True):
            import logging
            logging.getLogger(__name__).warning(
                "⚠️ FERNET_KEY غير مضبوط — البيانات الصحية بدون تشفير"
            )
            return None
        else:
            from django.core.exceptions import ImproperlyConfigured
            raise ImproperlyConfigured(
                "FERNET_KEY مطلوب في الإنتاج. أضفه إلى .env"
            )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        return None


def encrypt_field(value):
    if not value:
        return value
    f = _get_fernet()
    if not f:
        return value
    return f.encrypt(value.encode()).decode()


def decrypt_field(value):
    if not value:
        return value
    f = _get_fernet()
    if not f:
        return value
    try:
        return f.decrypt(value.encode()).decode()
    except Exception:
        return value

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.utils import timezone
from .managers import CustomUserManager


def _uuid():
    return uuid.uuid4()


class School(models.Model):
    id         = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    name       = models.CharField(max_length=200, verbose_name="اسم المدرسة")
    code       = models.CharField(max_length=10, unique=True, verbose_name="الكود")
    city       = models.CharField(max_length=100, verbose_name="المدينة", default="الشحانية")
    phone      = models.CharField(max_length=20, blank=True)
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "مدرسة"
        verbose_name_plural = "المدارس"

    def __str__(self):
        return f"{self.name} ({self.code})"


class CustomUser(AbstractBaseUser, PermissionsMixin):
    id          = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    national_id = models.CharField(max_length=20, unique=True, verbose_name="الرقم الوطني", db_index=True)
    full_name   = models.CharField(max_length=200, verbose_name="الاسم الكامل", db_index=True)
    email       = models.EmailField(blank=True, verbose_name="البريد الإلكتروني")
    phone       = models.CharField(max_length=20, blank=True, verbose_name="الجوال")
    is_staff              = models.BooleanField(default=False)
    is_active             = models.BooleanField(default=True)
    date_joined           = models.DateTimeField(default=timezone.now)
    # ── أمان الحساب ─────────────────────────────────────────
    must_change_password  = models.BooleanField(default=True,
        verbose_name="يجب تغيير كلمة المرور")
    totp_secret           = models.CharField(max_length=64, blank=True,
        verbose_name="مفتاح 2FA")
    totp_enabled          = models.BooleanField(default=False,
        verbose_name="2FA مفعّل")
    last_password_change  = models.DateTimeField(null=True, blank=True,
        verbose_name="آخر تغيير لكلمة المرور")
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until          = models.DateTimeField(null=True, blank=True,
        verbose_name="مقفل حتى")
    consent_given_at      = models.DateTimeField(null=True, blank=True,
        verbose_name="تاريخ إعطاء الموافقة")

    USERNAME_FIELD  = "national_id"
    REQUIRED_FIELDS = ["full_name"]
    objects         = CustomUserManager()

    class Meta:
        verbose_name        = "مستخدم"
        verbose_name_plural = "المستخدمون"

    def __str__(self):
        return f"{self.full_name} ({self.national_id})"

    @property
    def active_membership(self):
        if not hasattr(self, '_active_membership'):
            self._active_membership = self.memberships.filter(is_active=True).select_related("school", "role").first()
        return self._active_membership

    def get_active_membership(self):
        return self.active_membership

    @property
    def school(self):
        m = self.active_membership
        return m.school if m else None

    def get_school(self):
        return self.school

    @property
    def role(self):
        m = self.active_membership
        return m.role.name if m else None

    def get_role(self):
        return self.role or ""

    def has_role(self, role_name):
        """تحقق إذا كان المستخدم يملك دوراً معيناً (بغض النظر عن الدور الأساسي)"""
        return self.memberships.filter(
            is_active=True, role__name=role_name
        ).exists()

    def get_parent_membership(self):
        """إرجاع عضوية ولي الأمر إن وجدت — يدعم الموظف الذي هو أيضاً ولي أمر"""
        return self.memberships.filter(
            is_active=True, role__name="parent"
        ).select_related("school", "role").first()

    def is_admin(self):
        return self.is_superuser or self.get_role() in ("admin", "principal")

    def is_teacher(self):
        return self.get_role() in ("teacher", "coordinator")


class Profile(models.Model):
    GENDER = [("M", "ذكر"), ("F", "أنثى")]
    user       = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name="profile")
    gender     = models.CharField(max_length=1, choices=GENDER, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    notes      = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "ملف شخصي"

    def __str__(self):
        return f"Profile: {self.user.full_name}"


class Role(models.Model):
    ROLES = [
        ("principal",   "مدير المدرسة"),
        ("vice_admin",  "النائب الإداري"),
        ("vice_academic","النائب الأكاديمي"),
        ("coordinator", "منسق"),
        ("teacher",     "معلم"),
        ("specialist",  "أخصائي"),
        ("nurse",       "ممرض/ة"),
        ("librarian",   "أمين مكتبة"),
        ("bus_supervisor", "مشرف باص"),
        ("admin",       "إداري"),
        ("student",     "طالب"),
        ("parent",      "ولي أمر"),
    ]
    id     = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="roles")
    name   = models.CharField(max_length=30, choices=ROLES)

    class Meta:
        verbose_name        = "دور"
        verbose_name_plural = "الأدوار"
        constraints = [
            models.UniqueConstraint(fields=["school", "name"], name="unique_role_per_school")
        ]

    def __str__(self):
        return f"{self.get_name_display()} — {self.school.code}"


class Membership(models.Model):
    id        = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    user      = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="memberships")
    school    = models.ForeignKey(School, on_delete=models.CASCADE, related_name="memberships")
    role      = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="memberships")
    is_active = models.BooleanField(default=True)
    joined_at = models.DateField(default=timezone.now)

    class Meta:
        verbose_name        = "عضوية"
        verbose_name_plural = "العضويات"
        indexes = [models.Index(fields=["school", "role"])]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "school", "role"],
                condition=models.Q(is_active=True),
                name="unique_active_membership"
            )
        ]

    def __str__(self):
        return f"{self.user.full_name} | {self.role} | {self.school.code}"


class ClassGroup(models.Model):
    GRADES = [
        ("G7","الصف السابع"), ("G8","الصف الثامن"), ("G9","الصف التاسع"),
        ("G10","الصف العاشر"), ("G11","الصف الحادي عشر"), ("G12","الصف الثاني عشر"),
    ]
    LEVELS = [("prep","إعدادي"), ("sec","ثانوي")]

    id            = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school        = models.ForeignKey(School, on_delete=models.CASCADE, related_name="class_groups")
    grade         = models.CharField(max_length=3, choices=GRADES)
    section       = models.CharField(max_length=10, verbose_name="الشعبة")
    level_type    = models.CharField(max_length=4, choices=LEVELS, default="prep")
    academic_year = models.CharField(max_length=9, default="2025-2026")
    supervisor    = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name="supervised_classes")
    is_active     = models.BooleanField(default=True)

    class Meta:
        verbose_name        = "فصل دراسي"
        verbose_name_plural = "الفصول الدراسية"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "grade", "section", "academic_year"],
                name="unique_class_per_year"
            )
        ]
        indexes = [models.Index(fields=["school", "grade", "academic_year"])]

    def __str__(self):
        return f"{self.get_grade_display()} / {self.section} ({self.academic_year})"


class StudentEnrollment(models.Model):
    id          = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    student     = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="enrollments")
    class_group = models.ForeignKey(ClassGroup, on_delete=models.CASCADE, related_name="enrollments")
    is_active   = models.BooleanField(default=True)
    enrolled_at = models.DateField(default=timezone.now)

    class Meta:
        verbose_name = "تسجيل طالب"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "class_group"],
                condition=models.Q(is_active=True),
                name="unique_active_enrollment"
            )
        ]

    def __str__(self):
        return f"{self.student.full_name} → {self.class_group}"


class ParentStudentLink(models.Model):
    RELATIONSHIP = [
        ("father",   "الأب"),
        ("mother",   "الأم"),
        ("guardian", "الوصي"),
        ("other",    "أخرى"),
    ]

    id           = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school       = models.ForeignKey(School,      on_delete=models.CASCADE, related_name="parent_links")
    parent       = models.ForeignKey(CustomUser,  on_delete=models.CASCADE, related_name="children_links",  verbose_name="ولي الأمر")
    student      = models.ForeignKey(CustomUser,  on_delete=models.CASCADE, related_name="parent_links",    verbose_name="الطالب")
    relationship = models.CharField(max_length=20, choices=RELATIONSHIP, default="father", verbose_name="صلة القرابة")
    is_primary   = models.BooleanField(default=True,  verbose_name="ولي الأمر الأساسي")
    can_view_grades     = models.BooleanField(default=True, verbose_name="يرى الدرجات")
    can_view_attendance = models.BooleanField(default=True, verbose_name="يرى الغياب")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "ربط ولي أمر"
        verbose_name_plural = "ربط أولياء الأمور"
        ordering            = ["student__full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "student", "school"],
                name="unique_parent_student_school",
            )
        ]

    def __str__(self):
        return f"{self.parent.full_name} ← {self.student.full_name} ({self.get_relationship_display()})"



# ══════════════════════════════════════════════════════════════════════
# Backward-compatible re-exports
# النماذج نُقلت لتطبيقاتها — هذه السطور تحافظ على التوافق الخلفي
# from core.models import HealthRecord  ← لا يزال يعمل
# ══════════════════════════════════════════════════════════════════════
from clinic.models    import HealthRecord, ClinicVisit                    # noqa: F401,E402
from behavior.models  import BehaviorInfraction, BehaviorPointRecovery    # noqa: F401,E402
from transport.models import SchoolBus, BusRoute                          # noqa: F401,E402
from library.models   import LibraryBook, BookBorrowing, LibraryActivity  # noqa: F401,E402

class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('create',  'إنشاء'),
        ('update',  'تعديل'),
        ('delete',  'حذف'),
        ('view',    'عرض'),
        ('export',  'تصدير'),
        ('login',   'تسجيل دخول'),
        ('logout',  'تسجيل خروج'),
    ]
    MODEL_CHOICES = [
        ('HealthRecord',        'سجل صحي'),
        ('BehaviorInfraction',  'مخالفة سلوكية'),
        ('StudentSubjectResult','درجة طالب'),
        ('ClinicVisit',         'زيارة عيادة'),
        ('CustomUser',          'مستخدم'),
        ('ParentStudentLink',   'ربط ولي أمر'),
        ('BookBorrowing',       'إعارة كتاب'),
        ('ConsentRecord',       'سجل موافقة'),
        ('StudentAssessmentGrade', 'درجة تقييم'),
        ('other',               'أخرى'),
    ]

    id          = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school      = models.ForeignKey(School, on_delete=models.CASCADE,
                                    null=True, blank=True, related_name='audit_logs')
    user        = models.ForeignKey(CustomUser, on_delete=models.SET_NULL,
                                    null=True, related_name='audit_actions')
    action      = models.CharField(max_length=10, choices=ACTION_CHOICES)
    model_name  = models.CharField(max_length=50, choices=MODEL_CHOICES, default='other')
    object_id   = models.CharField(max_length=100, blank=True)
    object_repr = models.CharField(max_length=300, blank=True, verbose_name="وصف السجل")
    changes     = models.JSONField(null=True, blank=True, verbose_name="التغييرات")
    ip_address  = models.GenericIPAddressField(null=True, blank=True)
    user_agent  = models.CharField(max_length=300, blank=True)
    timestamp   = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name        = "سجل مراجعة"
        verbose_name_plural = "سجلات المراجعة"
        ordering            = ['-timestamp']
        indexes             = [
            models.Index(fields=['school', 'timestamp']),
            models.Index(fields=['model_name', 'object_id']),
            models.Index(fields=['user', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.user} | {self.action} | {self.model_name} | {self.timestamp:%Y-%m-%d %H:%M}"

    @classmethod
    def log(cls, *, user, action, model_name, object_id='', object_repr='',
            changes=None, school=None, request=None):
        ip = ua = ''
        if request:
            ip = request.META.get('REMOTE_ADDR')
            ua = request.META.get('HTTP_USER_AGENT', '')[:300]
            if not school and hasattr(request.user, 'get_school'):
                school = request.user.get_school()
        cls.objects.create(
            user=user, action=action, model_name=model_name,
            object_id=str(object_id), object_repr=str(object_repr)[:300],
            changes=changes, school=school,
            ip_address=ip, user_agent=ua,
        )


class ConsentRecord(models.Model):
    DATA_TYPES = [
        ('health',      'البيانات الصحية'),
        ('behavior',    'بيانات السلوك'),
        ('grades',      'الدرجات والتقييمات'),
        ('attendance',  'الحضور والغياب'),
        ('transport',   'بيانات النقل'),
        ('photo',       'الصور والمرئيات'),
        ('all',         'جميع البيانات'),
    ]
    METHODS = [
        ('form',    'استمارة ورقية'),
        ('digital', 'موافقة رقمية'),
        ('verbal',  'موافقة شفهية موثقة'),
    ]

    id            = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school        = models.ForeignKey(School, on_delete=models.CASCADE)
    parent        = models.ForeignKey(CustomUser, on_delete=models.CASCADE,
                                      related_name='consent_records')
    student       = models.ForeignKey(CustomUser, on_delete=models.CASCADE,
                                      related_name='consent_as_student')
    data_type     = models.CharField(max_length=20, choices=DATA_TYPES)
    is_given      = models.BooleanField(default=True, verbose_name="تمت الموافقة")
    method        = models.CharField(max_length=10, choices=METHODS, default='digital')
    given_at      = models.DateTimeField(auto_now_add=True)
    withdrawn_at  = models.DateTimeField(null=True, blank=True)
    notes         = models.TextField(blank=True)
    recorded_by   = models.ForeignKey(CustomUser, on_delete=models.SET_NULL,
                                      null=True, related_name='consents_recorded')

    class Meta:
        verbose_name        = "سجل موافقة"
        verbose_name_plural = "سجلات الموافقة"
        unique_together     = ('parent', 'student', 'data_type')
        ordering            = ['-given_at']

    def __str__(self):
        status = "موافق" if self.is_given else "مسحوب"
        return f"{self.parent.full_name} ← {self.student.full_name} | {self.get_data_type_display()} | {status}"

    def withdraw(self):
        from django.utils import timezone
        self.is_given     = False
        self.withdrawn_at = timezone.now()


# ════════════════════════════════════════════════════════════════════
# ✅ BreachNotification — v5 (PDPPL م.11 + NCSA 72 ساعة)
# ════════════════════════════════════════════════════════════════════

class BreachReport(models.Model):
    """
    تقرير خرق البيانات — PDPPL م.11
    يجب إشعار NCSA خلال 72 ساعة من اكتشاف الخرق
    """
    SEVERITY = [
        ('low',      'منخفضة'),
        ('medium',   'متوسطة'),
        ('high',     'عالية'),
        ('critical', 'حرجة'),
    ]
    STATUS = [
        ('discovered',  'مكتشف'),
        ('assessing',   'قيد التقييم'),
        ('notified',    'تم الإشعار'),
        ('resolved',    'محلول'),
    ]
    DATA_TYPES_AFFECTED = [
        ('health',    'بيانات صحية'),
        ('academic',  'بيانات أكاديمية'),
        ('personal',  'بيانات شخصية'),
        ('financial', 'بيانات مالية'),
        ('all',       'جميع البيانات'),
    ]

    id                  = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school              = models.ForeignKey(School, on_delete=models.CASCADE,
                                            related_name='breach_reports')
    # بيانات الخرق
    title               = models.CharField(max_length=300, verbose_name='عنوان الخرق')
    description         = models.TextField(verbose_name='وصف الخرق التفصيلي')
    severity            = models.CharField(max_length=10, choices=SEVERITY, default='medium')
    data_type_affected  = models.CharField(max_length=15, choices=DATA_TYPES_AFFECTED,
                                           default='personal', verbose_name='نوع البيانات المتأثرة')
    affected_count      = models.PositiveIntegerField(default=0,
                                                      verbose_name='عدد الأشخاص المتأثرين')
    # التوقيتات
    discovered_at       = models.DateTimeField(verbose_name='وقت الاكتشاف')
    created_at          = models.DateTimeField(auto_now_add=True)
    ncsa_deadline       = models.DateTimeField(null=True, blank=True,
                                               verbose_name='موعد إشعار NCSA (72 ساعة)')
    ncsa_notified_at    = models.DateTimeField(null=True, blank=True,
                                               verbose_name='وقت إشعار NCSA الفعلي')
    resolved_at         = models.DateTimeField(null=True, blank=True)
    # الحالة والمسؤولية
    status              = models.CharField(max_length=15, choices=STATUS, default='discovered')
    reported_by         = models.ForeignKey(CustomUser, on_delete=models.SET_NULL,
                                            null=True, related_name='reported_breaches')
    assigned_to         = models.ForeignKey(CustomUser, on_delete=models.SET_NULL,
                                            null=True, blank=True,
                                            related_name='assigned_breaches',
                                            verbose_name='المسؤول (DPO)')
    # الإجراءات
    immediate_action    = models.TextField(blank=True, verbose_name='الإجراء الفوري المتخذ')
    containment_action  = models.TextField(blank=True, verbose_name='إجراءات الاحتواء')
    notification_text   = models.TextField(blank=True, verbose_name='نص الإشعار لـ NCSA')
    # المرفقات
    evidence_notes      = models.TextField(blank=True, verbose_name='الأدلة والملاحظات')

    class Meta:
        verbose_name        = 'تقرير خرق بيانات'
        verbose_name_plural = 'تقارير خرق البيانات'
        ordering            = ['-discovered_at']
        indexes             = [
            models.Index(fields=['school', 'status']),
            models.Index(fields=['discovered_at']),
        ]

    def __str__(self):
        return f"{self.title} | {self.get_severity_display()} | {self.get_status_display()}"

    def save(self, *args, **kwargs):
        """احسب deadline تلقائياً: 72 ساعة من الاكتشاف"""
        from datetime import timedelta
        if self.discovered_at and not self.ncsa_deadline:
            self.ncsa_deadline = self.discovered_at + timedelta(hours=72)
        super().save(*args, **kwargs)

    @property
    def hours_remaining(self):
        """الساعات المتبقية قبل انتهاء مهلة NCSA"""
        from django.utils import timezone
        if self.ncsa_deadline and self.status not in ('notified', 'resolved'):
            delta = self.ncsa_deadline - timezone.now()
            return max(0, int(delta.total_seconds() / 3600))
        return None

    @property
    def is_overdue(self):
        """هل تجاوزت المهلة؟"""
        from django.utils import timezone
        return (
            self.ncsa_deadline and
            timezone.now() > self.ncsa_deadline and
            self.status not in ('notified', 'resolved')
        )
