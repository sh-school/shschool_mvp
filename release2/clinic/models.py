"""
clinic/models.py
نماذج العيادة المدرسية — نُقلت من core/models.py
db_table مضبوط صراحةً لإبقاء نفس الجداول في قاعدة البيانات
"""
import uuid
from django.db import models


def _uuid():
    return uuid.uuid4()


class HealthRecord(models.Model):
    """السجل الصحي للطالب — البيانات الحساسة مشفرة بـ Fernet"""
    BLOOD_TYPES = [
        ('A+', 'A+'), ('A-', 'A-'), ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'), ('O+', 'O+'), ('O-', 'O-'),
    ]
    id               = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    student          = models.OneToOneField(
        'core.CustomUser', on_delete=models.CASCADE, related_name="health_record"
    )
    blood_type       = models.CharField(max_length=3, choices=BLOOD_TYPES, blank=True)
    allergies        = models.TextField(blank=True, verbose_name="الحساسية")
    chronic_diseases = models.TextField(blank=True, verbose_name="الأمراض المزمنة")
    medications      = models.TextField(blank=True, verbose_name="الأدوية المستمرة")
    emergency_contact_name  = models.CharField(max_length=200, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "سجل صحي"
        verbose_name_plural = "السجلات الصحية"
        db_table            = "core_healthrecord"   # يبقي نفس الجدول الموجود

    def __str__(self):
        return f"Health Record: {self.student.full_name}"

    # ── Fernet encryption helpers ─────────────────────────────────
    def _encrypt(self, value):
        from core.models import encrypt_field
        return encrypt_field(value)

    def _decrypt(self, value):
        from core.models import decrypt_field
        return decrypt_field(value)

    def get_allergies(self):
        return self._decrypt(self.allergies)

    def set_allergies(self, value):
        self.allergies = self._encrypt(value)

    def get_chronic_diseases(self):
        return self._decrypt(self.chronic_diseases)

    def set_chronic_diseases(self, value):
        self.chronic_diseases = self._encrypt(value)

    def get_medications(self):
        return self._decrypt(self.medications)

    def set_medications(self, value):
        self.medications = self._encrypt(value)

    def save_encrypted(self, allergies="", chronic_diseases="", medications="", **kwargs):
        self.set_allergies(allergies)
        self.set_chronic_diseases(chronic_diseases)
        self.set_medications(medications)
        self.save(**kwargs)


class ClinicVisit(models.Model):
    """زيارة عيادة — يُرسَل إشعار لولي الأمر عند الإرسال للمنزل"""
    id              = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school          = models.ForeignKey('core.School', on_delete=models.CASCADE)
    student         = models.ForeignKey(
        'core.CustomUser', on_delete=models.CASCADE, related_name="clinic_visits"
    )
    nurse           = models.ForeignKey(
        'core.CustomUser', on_delete=models.SET_NULL, null=True, related_name="nurse_visits"
    )
    visit_date      = models.DateTimeField(auto_now_add=True)
    reason          = models.TextField(verbose_name="سبب الزيارة")
    symptoms        = models.TextField(blank=True, verbose_name="الأعراض")
    temperature     = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    treatment       = models.TextField(blank=True, verbose_name="الإجراء المتخذ")
    is_sent_home    = models.BooleanField(default=False, verbose_name="تم إرساله للمنزل")
    parent_notified = models.BooleanField(default=False, verbose_name="تم إبلاغ ولي الأمر")

    class Meta:
        verbose_name        = "زيارة عيادة"
        verbose_name_plural = "زيارات العيادة"
        ordering            = ['-visit_date']
        db_table            = "core_clinicvisit"   # يبقي نفس الجدول الموجود

    def __str__(self):
        return f"Visit: {self.student.full_name} - {self.visit_date.date()}"
