import uuid
from django.db import models
from core.models import School, CustomUser, ClassGroup, _uuid

# ─────────────────────────────────────────────────────────────
# 1. وحدة العيادة المدرسية (School Clinic)
# ─────────────────────────────────────────────────────────────

class HealthRecord(models.Model):
    """السجل الصحي للطالب"""
    BLOOD_TYPES = [
        ('A+', 'A+'), ('A-', 'A-'), ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'), ('O+', 'O+'), ('O-', 'O-'),
    ]
    id             = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    student        = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name="health_record")
    blood_type     = models.CharField(max_length=3, choices=BLOOD_TYPES, blank=True)
    allergies      = models.TextField(blank=True, verbose_name="الحساسية")
    chronic_diseases = models.TextField(blank=True, verbose_name="الأمراض المزمنة")
    medications    = models.TextField(blank=True, verbose_name="الأدوية المستمرة")
    emergency_contact_name = models.CharField(max_length=200, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "سجل صحي"
        verbose_name_plural = "السجلات الصحية"

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

# ─────────────────────────────────────────────────────────────
# 2. وحدة النقل والمواصلات (School Transport)
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

class BusRoute(models.Model):
    """خط سير الحافلة والطلاب المشتركين"""
    id           = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    bus          = models.ForeignKey(SchoolBus, on_delete=models.CASCADE, related_name="routes")
    area_name    = models.CharField(max_length=200, verbose_name="المنطقة")
    students     = models.ManyToManyField(CustomUser, related_name="bus_routes", verbose_name="الطلاب")

    class Meta:
        verbose_name = "خط سير"
        verbose_name_plural = "خطوط السير"

# ─────────────────────────────────────────────────────────────
# 3. وحدة السلوك الطلابي (Student Behavior)
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
    level        = models.PositiveSmallIntegerField(choices=LEVELS, default=1)
    description  = models.TextField(verbose_name="وصف المخالفة")
    action_taken = models.TextField(blank=True, verbose_name="الإجراء المتخذ")
    points_deducted = models.PositiveIntegerField(default=0, verbose_name="النقاط المخصومة")
    is_resolved  = models.BooleanField(default=False)

    class Meta:
        verbose_name = "مخالفة سلوكية"
        verbose_name_plural = "المخالفات السلوكية"
        ordering = ['-date']

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

# ─────────────────────────────────────────────────────────────
# 4. وحدة المكتبة ومصادر التعلم (Library & Learning Resources)
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
        ordering = ['-borrow_date']

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
