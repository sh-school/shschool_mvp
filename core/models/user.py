from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from ..managers import CustomUserManager
from ._crypto import decrypt_field, encrypt_field, hmac_field
from .school import _uuid

_national_id_validator = RegexValidator(
    regex=r"^\d{5,20}$",
    message="الرقم الوطني يجب أن يحتوي على أرقام فقط (5-20 رقم)",
)
_phone_validator = RegexValidator(
    regex=r"^\+?[\d\s\-]{7,20}$",
    message="رقم الجوال غير صحيح — استخدم صيغة دولية مثل +97455xxxxxx",
)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    national_id = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="الرقم الوطني",
        db_index=True,
        validators=[_national_id_validator],
    )
    full_name = models.CharField(max_length=200, verbose_name="الاسم الكامل", db_index=True)
    email = models.EmailField(blank=True, verbose_name="البريد الإلكتروني")
    phone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="الجوال",
        validators=[_phone_validator],
    )
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)
    must_change_password = models.BooleanField(default=True, verbose_name="يجب تغيير كلمة المرور")
    totp_secret = models.CharField(max_length=255, blank=True, verbose_name="مفتاح 2FA")
    totp_enabled = models.BooleanField(default=False, verbose_name="2FA مفعّل")
    last_password_change = models.DateTimeField(
        null=True, blank=True, verbose_name="آخر تغيير لكلمة المرور"
    )
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True, verbose_name="مقفل حتى")
    consent_given_at = models.DateTimeField(
        null=True, blank=True, verbose_name="تاريخ إعطاء الموافقة"
    )

    # ── v6: الرخصة المهنية — نظام الرخص المهنية (قطر) ──────────────
    professional_license_number = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="رقم الرخصة المهنية",
        help_text="رقم الرخصة الصادرة من وزارة التعليم والتعليم العالي",
    )
    professional_license_expiry = models.DateField(
        null=True,
        blank=True,
        verbose_name="تاريخ انتهاء الرخصة المهنية",
    )

    # ── v5.1.1: HMAC + Fernet encryption for national_id (PDPPL) ──
    national_id_encrypted = models.TextField(
        blank=True,
        default="",
        verbose_name="الرقم الوطني (مشفّر)",
    )
    national_id_hmac = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        verbose_name="HMAC الرقم الوطني",
    )

    USERNAME_FIELD = "national_id"
    REQUIRED_FIELDS = ["full_name"]
    objects = CustomUserManager()

    class Meta:
        verbose_name = "مستخدم"
        verbose_name_plural = "المستخدمون"

    def __str__(self):
        return f"{self.full_name} ({self.national_id})"

    def save(self, *args, **kwargs):
        # ── Auto-populate HMAC + Fernet fields on every save ──
        if self.national_id:
            new_hmac = hmac_field(self.national_id)
            if new_hmac != self.national_id_hmac:
                self.national_id_hmac = new_hmac
            new_enc = encrypt_field(self.national_id)
            if new_enc and new_enc != self.national_id_encrypted:
                self.national_id_encrypted = new_enc
        super().save(*args, **kwargs)

    def get_national_id_decrypted(self):
        """فك تشفير الرقم الوطني من الحقل المشفّر — fallback إلى الحقل العادي."""
        if self.national_id_encrypted:
            decrypted = decrypt_field(self.national_id_encrypted)
            if decrypted and decrypted != self.national_id_encrypted:
                return decrypted
        return self.national_id

    @property
    def active_membership(self):
        cached = self.__dict__.get("_active_membership")
        if cached is not None:
            return cached
        result = self.memberships.filter(is_active=True).select_related("school", "role").first()
        if result is not None:
            self.__dict__["_active_membership"] = result
        return result

    def invalidate_active_membership(self):
        """يُبطل cache العضوية — استخدمه بعد إنشاء أو تعديل Membership"""
        self.__dict__.pop("_active_membership", None)

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
        return self.memberships.filter(is_active=True, role__name=role_name).exists()

    def has_any_role(self, *role_names):
        """يتحقق من أن المستخدم لديه أحد الأدوار المعطاة (أسرع من استدعاء has_role عدة مرات)."""
        return self.get_role() in role_names

    def get_parent_membership(self):
        return (
            self.memberships.filter(is_active=True, role__name="parent")
            .select_related("school", "role")
            .first()
        )

    @property
    def department(self):
        """يُعيد اسم قسم/تخصص المستخدم — من FK (v6)."""
        m = self.active_membership
        if not m:
            return ""
        if m.department_obj_id:
            return m.department_obj.name
        return ""

    @property
    def department_obj(self):
        """يُعيد كائن Department مباشرة (أو None)."""
        m = self.active_membership
        return m.department_obj if m and m.department_obj_id else None

    def get_department(self):
        return self.department

    def is_admin(self):
        """مدير أو superuser — صلاحيات إدارية كاملة."""
        return self.is_superuser or self.get_role() in ("admin", "principal")

    def is_admin_or_principal(self):
        """مدير المدرسة أو نوابه — للقرارات الإدارية العليا."""
        return self.is_superuser or self.get_role() in (
            "principal", "vice_admin", "vice_academic", "admin",
        )

    def is_teacher(self):
        return self.get_role() in ("teacher", "coordinator", "ese_teacher")

    def is_leadership(self):
        """المستوى الأول والثاني — القيادة العليا ونواب المدير."""
        return self.is_superuser or self.get_role() in (
            "principal", "vice_admin", "vice_academic",
        )

    def is_staff_member(self):
        """أي دور من الطاقم (ليس طالب أو ولي أمر)."""
        from .access import ALL_STAFF_ROLES
        return self.is_superuser or self.get_role() in ALL_STAFF_ROLES or self.get_role() == "specialist"

    def is_same_department(self, other_department):
        """
        يتحقق إذا كان المستخدم من نفس القسم/التخصص.
        يقبل: اسم نصي أو كائن Department.
        """
        from .department import Department

        if isinstance(other_department, Department):
            my_dept = self.department_obj
            return my_dept is not None and my_dept.pk == other_department.pk
        # مقارنة نصية — يقرأ من FK
        my_dept_name = self.department
        return bool(my_dept_name) and my_dept_name == other_department


class Profile(models.Model):
    GENDER = [("M", "ذكر"), ("F", "أنثى")]
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name="profile")
    gender = models.CharField(max_length=1, choices=GENDER, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "ملف شخصي"

    def __str__(self):
        return f"Profile: {self.user.full_name}"
