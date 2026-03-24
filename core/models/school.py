import uuid

from django.db import models


def _uuid():
    return uuid.uuid4()


class School(models.Model):
    """نموذج المدرسة — يشمل جميع البيانات الأساسية والإدارية."""

    # ── نوع المدرسة ──────────────────────────────────────────────
    SCHOOL_TYPE = [
        ("boys", "بنين"),
        ("girls", "بنات"),
        ("mixed", "مختلط"),
    ]

    EDUCATION_LEVEL = [
        ("primary", "ابتدائي"),
        ("preparatory", "إعدادي"),
        ("secondary", "ثانوي"),
        ("prep_sec", "إعدادي + ثانوي"),
        ("all", "جميع المراحل"),
    ]

    # ── المعرّفات ─────────────────────────────────────────────────
    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    name = models.CharField(max_length=200, verbose_name="اسم المدرسة")
    code = models.CharField(max_length=10, unique=True, verbose_name="كود المدرسة")
    abbreviation = models.CharField(
        max_length=10,
        blank=True,
        verbose_name="الاختصار",
        help_text="مثلاً: SHH",
    )
    ministry_code = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="رمز الوزارة",
        help_text="رمز المدرسة في وزارة التربية والتعليم",
    )

    # ── النوع والمرحلة ────────────────────────────────────────────
    school_type = models.CharField(
        max_length=10,
        choices=SCHOOL_TYPE,
        default="boys",
        verbose_name="نوع المدرسة",
    )
    education_level = models.CharField(
        max_length=15,
        choices=EDUCATION_LEVEL,
        default="prep_sec",
        verbose_name="المرحلة الدراسية",
    )
    established_year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="سنة التأسيس",
    )

    # ── الاتصال ───────────────────────────────────────────────────
    phone = models.CharField(max_length=20, blank=True, verbose_name="الهاتف")
    fax = models.CharField(max_length=20, blank=True, verbose_name="الفاكس")
    email = models.EmailField(blank=True, verbose_name="البريد الإلكتروني")
    website = models.URLField(blank=True, verbose_name="الموقع الإلكتروني")

    # ── العنوان ───────────────────────────────────────────────────
    city = models.CharField(max_length=100, verbose_name="المدينة", default="الشحانية")
    zone = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="المنطقة / الحي",
    )
    address = models.TextField(
        blank=True,
        verbose_name="العنوان التفصيلي",
    )
    po_box = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="صندوق البريد",
    )

    # ── الإدارة ───────────────────────────────────────────────────
    principal = models.ForeignKey(
        "core.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="principal_of",
        verbose_name="المدير",
        help_text="اختر المدير من قائمة المستخدمين",
    )

    # ── الهوية البصرية ────────────────────────────────────────────
    logo = models.ImageField(
        upload_to="schools/logos/",
        blank=True,
        null=True,
        verbose_name="شعار المدرسة",
        help_text="يُفضل PNG شفاف بحجم 200x200 بكسل على الأقل",
    )

    # ── النظام ────────────────────────────────────────────────────
    is_active = models.BooleanField(default=True, verbose_name="نشطة")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "مدرسة"
        verbose_name_plural = "المدارس"

    def __str__(self):
        return f"{self.name} ({self.code})"
