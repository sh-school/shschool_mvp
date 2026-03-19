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
    """احصل على مثيل Fernet — يُنبّه إذا غاب المفتاح"""
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
    """تشفير قيمة نصية — تُعيد نفس القيمة إذا لم يتوفر مفتاح"""
    if not value:
        return value
    f = _get_fernet()
    if not f:
        return value
    return f.encrypt(value.encode()).decode()


def decrypt_field(value):
    """فك تشفير قيمة — تُعيد نفس القيمة إذا لم تكن مشفرة"""
    if not value:
        return value
    f = _get_fernet()
    if not f:
        return value
    try:
        return f.decrypt(value.encode()).decode()
    except Exception:
        return value  # إذا لم تكن مشفرة أصلاً
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
    is_staff    = models.BooleanField(default=False)
    is_active   = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

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
        # تخزين العضوية النشطة في الـ session بعد أول استدعاء
        if not hasattr(self, '_active_membership'):
            self._active_membership = self.memberships.filter(is_active=True).select_related("school", "role").first()
        return self._active_membership

    def get_active_membership(self):
        # هذه الدالة موجودة للتوافقية، يفضل استخدام خاصية active_membership
        return self.active_membership

    @property
    def school(self):
        m = self.active_membership
        return m.school if m else None

    def get_school(self):
        # هذه الدالة موجودة للتوافقية، يفضل استخدام خاصية school
        return self.school

    @property
    def role(self):
        m = self.active_membership
        return m.role.name if m else None

    def get_role(self):
        # هذه الدالة موجودة للتوافقية، يفضل استخدام خاصية role
        return self.role or ""

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


# ─────────────────────────────────────────────────────────────
# ربط ولي الأمر بأبنائه ← جديد
# ─────────────────────────────────────────────────────────────

class ParentStudentLink(models.Model):
    """ربط حساب ولي الأمر بالطالب مع تحديد الصلاحيات"""
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

    # صلاحيات العرض
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


# ─────────────────────────────────────────────────────────────
# 1. وحدة العيادة المدرسية (School Clinic) ← جديد
# ─────────────────────────────────────────────────────────────

class HealthRecord(models.Model):
    """السجل الصحي للطالب — الحقول الحساسة مُشفَّرة بـ Fernet (PDPPL)"""
    BLOOD_TYPES = [
        ('A+', 'A+'), ('A-', 'A-'), ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'), ('O+', 'O+'), ('O-', 'O-'),
    ]
    id             = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    student        = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name="health_record")
    blood_type     = models.CharField(max_length=3, choices=BLOOD_TYPES, blank=True)
    # ⚠️ هذه الحقول تُخزَّن مُشفَّرة في DB — استخدم get_*/set_* للوصول
    allergies      = models.TextField(blank=True, verbose_name="الحساسية")
    chronic_diseases = models.TextField(blank=True, verbose_name="الأمراض المزمنة")
    medications    = models.TextField(blank=True, verbose_name="الأدوية المستمرة")
    emergency_contact_name = models.CharField(max_length=200, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "سجل صحي"
        verbose_name_plural = "السجلات الصحية"

    def __str__(self):
        return f"Health Record: {self.student.full_name}"

    # ── وصول آمن للحقول المشفرة ───────────────────────────
    def get_allergies(self):
        return decrypt_field(self.allergies)

    def set_allergies(self, value):
        self.allergies = encrypt_field(value)

    def get_chronic_diseases(self):
        return decrypt_field(self.chronic_diseases)

    def set_chronic_diseases(self, value):
        self.chronic_diseases = encrypt_field(value)

    def get_medications(self):
        return decrypt_field(self.medications)

    def set_medications(self, value):
        self.medications = encrypt_field(value)

    def save_encrypted(self, allergies="", chronic_diseases="", medications="", **kwargs):
        """احفظ بعد تشفير الحقول الحساسة"""
        self.set_allergies(allergies)
        self.set_chronic_diseases(chronic_diseases)
        self.set_medications(medications)
        self.save(**kwargs)


class ClinicVisit(models.Model):
    """زيارة للعيادة المدرسية"""
    id           = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school       = models.ForeignKey(School, on_delete=models.CASCADE)
    student      = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="clinic_visits")
    nurse        = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name="nurse_visits")
    visit_date   = models.DateTimeField(auto_now_add=True)
    reason       = models.TextField(verbose_name="سبب الزيارة")
    symptoms     = models.TextField(blank=True, verbose_name="الأعراض")
    temperature  = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    treatment    = models.TextField(blank=True, verbose_name="الإجراء المتخذ")
    is_sent_home = models.BooleanField(default=False, verbose_name="تم إرساله للمنزل")
    parent_notified = models.BooleanField(default=False, verbose_name="تم إبلاغ ولي الأمر")

    class Meta:
        verbose_name = "زيارة عيادة"
        verbose_name_plural = "زيارات العيادة"
        ordering = ['-visit_date']

    def __str__(self):
        return f"Visit: {self.student.full_name} - {self.visit_date.date()}"


# ─────────────────────────────────────────────────────────────
# 2. وحدة النقل والمواصلات (School Transport) ← جديد
# ─────────────────────────────────────────────────────────────

class SchoolBus(models.Model):
    """بيانات الحافلة المدرسية"""
    id           = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school       = models.ForeignKey(School, on_delete=models.CASCADE, related_name="buses")
    bus_number   = models.CharField(max_length=20, verbose_name="رقم الحافلة")
    driver_name  = models.CharField(max_length=200, verbose_name="اسم السائق")
    driver_phone = models.CharField(max_length=20, verbose_name="جوال السائق")
    supervisor   = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name="supervised_buses", verbose_name="مشرف الباص")
    capacity     = models.PositiveIntegerField(default=30)
    karwa_id     = models.CharField(max_length=50, blank=True, verbose_name="رقم كروة (Karwa ID)")
    gps_link     = models.URLField(blank=True, verbose_name="رابط التتبع (GPS)")

    class Meta:
        verbose_name = "حافلة مدرسية"
        verbose_name_plural = "الحافلات المدرسية"

    def __str__(self):
        return f"Bus {self.bus_number} - {self.school.code}"


class BusRoute(models.Model):
    """خط سير الحافلة والطلاب المشتركين"""
    id           = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    bus          = models.ForeignKey(SchoolBus, on_delete=models.CASCADE, related_name="routes")
    area_name    = models.CharField(max_length=200, verbose_name="المنطقة")
    students     = models.ManyToManyField(CustomUser, related_name="bus_routes", verbose_name="الطلاب")

    class Meta:
        verbose_name = "خط سير"
        verbose_name_plural = "خطوط السير"

    def __str__(self):
        return f"{self.bus.bus_number} - {self.area_name}"


# ─────────────────────────────────────────────────────────────
# 3. وحدة السلوك الطلابي (Student Behavior) ← جديد
# ─────────────────────────────────────────────────────────────

class BehaviorInfraction(models.Model):
    """مخالفة سلوكية حسب اللائحة القطرية"""
    LEVELS = [
        (1, 'الدرجة الأولى (بسيطة)'),
        (2, 'الدرجة الثانية (متوسطة)'),
        (3, 'الدرجة الثالثة (جسيمة)'),
        (4, 'الدرجة الرابعة (شديدة الخطورة)'),
    ]
    id           = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school       = models.ForeignKey(School, on_delete=models.CASCADE)
    student      = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="behavior_infractions")
    reported_by  = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name="reported_infractions")
    date         = models.DateField(auto_now_add=True)
    created_at   = models.DateTimeField(auto_now_add=True, null=True)
    level        = models.PositiveSmallIntegerField(choices=LEVELS, default=1)
    description  = models.TextField(verbose_name="وصف المخالفة")
    action_taken = models.TextField(blank=True, verbose_name="الإجراء المتخذ")
    points_deducted = models.PositiveIntegerField(default=0, verbose_name="النقاط المخصومة")
    is_resolved  = models.BooleanField(default=False)

    class Meta:
        verbose_name = "مخالفة سلوكية"
        verbose_name_plural = "المخالفات السلوكية"
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.student.full_name} - {self.get_level_display()}"


class BehaviorPointRecovery(models.Model):
    """فرصة لاستعادة النقاط المخصومة (التعزيز الإيجابي)"""
    id           = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    infraction   = models.OneToOneField(BehaviorInfraction, on_delete=models.CASCADE, related_name="recovery")
    reason       = models.TextField(verbose_name="سبب استعادة النقاط (سلوك إيجابي)")
    points_restored = models.PositiveIntegerField(default=0)
    approved_by  = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    date         = models.DateField(auto_now_add=True)

    class Meta:
        verbose_name = "استعادة نقاط"
        verbose_name_plural = "استعادة النقاط"

    def __str__(self):
        return f"Recovery: {self.infraction.student.full_name} (+{self.points_restored})"


# ─────────────────────────────────────────────────────────────
# 4. وحدة المكتبة ومصادر التعلم (Library & Learning Resources) ← جديد
# ─────────────────────────────────────────────────────────────

class LibraryBook(models.Model):
    """بيانات الكتب والمصادر في المكتبة المدرسية"""
    BOOK_TYPES = [
        ('PRINT', 'مطبوع'),
        ('DIGITAL', 'رقمي / PDF'),
        ('PERIODICAL', 'دورية / مجلة'),
    ]
    id           = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school       = models.ForeignKey(School, on_delete=models.CASCADE, related_name="library_books")
    title        = models.CharField(max_length=500, verbose_name="عنوان الكتاب")
    author       = models.CharField(max_length=200, verbose_name="المؤلف")
    isbn         = models.CharField(max_length=20, blank=True, verbose_name="ISBN")
    category     = models.CharField(max_length=100, verbose_name="التصنيف (ديوي العشري)")
    book_type    = models.CharField(max_length=20, choices=BOOK_TYPES, default='PRINT')
    quantity     = models.PositiveIntegerField(default=1, verbose_name="الكمية المتوفرة")
    available_qty = models.PositiveIntegerField(default=1, verbose_name="الكمية المتاحة للإعارة")
    digital_file = models.FileField(upload_to='library/digital/', null=True, blank=True, verbose_name="الملف الرقمي")
    location     = models.CharField(max_length=100, blank=True, verbose_name="موقع الكتاب (الرف)")

    class Meta:
        verbose_name = "كتاب مكتبة"
        verbose_name_plural = "كتب المكتبة"

    def __str__(self):
        return f"{self.title} - {self.author}"


class BookBorrowing(models.Model):
    """سجل إعارة الكتب للطلاب والموظفين"""
    STATUS = [
        ('BORROWED', 'قيد الإعارة'),
        ('RETURNED', 'تم الإرجاع'),
        ('OVERDUE', 'متأخر'),
        ('LOST', 'مفقود'),
    ]
    id           = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    book         = models.ForeignKey(LibraryBook, on_delete=models.CASCADE, related_name="borrowings")
    user         = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="borrowed_books", verbose_name="المستعير")
    borrow_date  = models.DateField(auto_now_add=True)
    due_date     = models.DateField(verbose_name="تاريخ الإرجاع المتوقع")
    return_date  = models.DateField(null=True, blank=True, verbose_name="تاريخ الإرجاع الفعلي")
    status       = models.CharField(max_length=20, choices=STATUS, default='BORROWED')
    librarian    = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name="processed_borrowings", verbose_name="أمين المكتبة")

    class Meta:
        verbose_name = "عملية إعارة"
        verbose_name_plural = "عمليات الإعارة"
        ordering = ['-borrow_date', '-id']

    def __str__(self):
        return f"{self.user.full_name} - {self.book.title}"


class LibraryActivity(models.Model):
    """الأنشطة الثقافية والقرائية في المكتبة"""
    id           = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school       = models.ForeignKey(School, on_delete=models.CASCADE)
    title        = models.CharField(max_length=200, verbose_name="اسم النشاط")
    description  = models.TextField(verbose_name="وصف النشاط")
    date         = models.DateField()
    participants = models.ManyToManyField(CustomUser, related_name="library_activities", verbose_name="المشاركون")
    outcome      = models.TextField(blank=True, verbose_name="مخرجات النشاط")

    class Meta:
        verbose_name = "نشاط مكتبة"
        verbose_name_plural = "أنشطة المكتبة"

    def __str__(self):
        return f"{self.title} - {self.date}"


# ─────────────────────────────────────────────────────────────
# AuditLog — سجل العمليات الحساسة (PDPPL / RoPA)
# ─────────────────────────────────────────────────────────────

class AuditLog(models.Model):
    """سجل شامل لكل العمليات الحساسة — مطلوب بموجب PDPPL"""
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
        """اختصار لتسجيل حدث"""
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


# ─────────────────────────────────────────────────────────────
# ConsentRecord — موافقة ولي الأمر على معالجة البيانات (PDPPL)
# ─────────────────────────────────────────────────────────────

class ConsentRecord(models.Model):
    """تسجيل موافقة ولي الأمر لكل نوع من أنواع معالجة البيانات"""
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
        self.save(update_fields=['is_given', 'withdrawn_at'])
