"""
clinic/models.py
نماذج العيادة المدرسية — نُقلت من core/models.py
db_table مضبوط صراحةً لإبقاء نفس الجداول في قاعدة البيانات
"""

import uuid

from django.db import models

from core.fields import EncryptedTextField

from .querysets import ClinicVisitQuerySet


def _uuid():
    return uuid.uuid4()


class HealthRecord(models.Model):
    """السجل الصحي للطالب — البيانات الحساسة مشفرة بـ Fernet"""

    BLOOD_TYPES = [
        ("A+", "A+"),
        ("A-", "A-"),
        ("B+", "B+"),
        ("B-", "B-"),
        ("AB+", "AB+"),
        ("AB-", "AB-"),
        ("O+", "O+"),
        ("O-", "O-"),
    ]
    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    student = models.OneToOneField(
        "core.CustomUser", on_delete=models.CASCADE, related_name="health_record"
    )
    blood_type = models.CharField(max_length=3, choices=BLOOD_TYPES, blank=True)
    # [PII-11] الحقولُ الطبّيّةُ الثلاثة كانت `TextField` تُشفَّر يدوياً عبر
    # `save_encrypted()`، بينما جهةُ الطوارئ تحتها `EncryptedTextField`. ومن
    # هذا الازدواج نشأ عيبٌ منشور: القالبُ يطبع الحقلَ الخام فتُعرض الطلاسمُ
    # في مربّع الإدخال، وأيُّ حفظٍ بعده يشفّرها من جديد.
    #
    # فوُحّدت على الحقل الشفّاف: النموذجُ يشفّر ويفكّ، ولا يبقى الأمرُ معلَّقاً
    # بانضباط كلّ شاشةٍ تكتب أو تقرأ.
    allergies = EncryptedTextField(blank=True, verbose_name="الحساسية")
    chronic_diseases = EncryptedTextField(blank=True, verbose_name="الأمراض المزمنة")
    medications = EncryptedTextField(blank=True, verbose_name="الأدوية المستمرة")
    # [PII-04] بيانات جهة اتصال الطوارئ (طرف ثالث بجوار سجل صحي لقاصر) — مشفّرة at-rest
    emergency_contact_name = EncryptedTextField(blank=True)
    emergency_contact_phone = EncryptedTextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "سجل صحي"
        verbose_name_plural = "السجلات الصحية"
        db_table = "core_healthrecord"  # يبقي نفس الجدول الموجود

    def __str__(self):
        return f"Health Record: {self.student.full_name}"


class ClinicVisit(models.Model):
    """زيارة عيادة — يُرسَل إشعار لولي الأمر عند الإرسال للمنزل"""

    objects = ClinicVisitQuerySet.as_manager()

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey("core.School", on_delete=models.CASCADE)
    student = models.ForeignKey(
        "core.CustomUser", on_delete=models.CASCADE, related_name="clinic_visits"
    )
    nurse = models.ForeignKey(
        "core.CustomUser", on_delete=models.SET_NULL, null=True, related_name="nurse_visits"
    )
    visit_date = models.DateTimeField(auto_now_add=True)
    # بيانات صحية حسّاسة (م.8 PDPPL) — مشفّرة at-rest بـ Fernet
    reason = EncryptedTextField(verbose_name="سبب الزيارة")
    symptoms = EncryptedTextField(blank=True, verbose_name="الأعراض")
    temperature = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    treatment = EncryptedTextField(blank=True, verbose_name="الإجراء المتخذ")
    is_sent_home = models.BooleanField(default=False, verbose_name="تم إرساله للمنزل")
    parent_notified = models.BooleanField(default=False, verbose_name="تم إبلاغ ولي الأمر")

    class Meta:
        verbose_name = "زيارة عيادة"
        verbose_name_plural = "زيارات العيادة"
        ordering = ["-visit_date"]
        db_table = "core_clinicvisit"  # يبقي نفس الجدول الموجود

    def __str__(self):
        return f"Visit: {self.student.full_name} - {self.visit_date.date()}"
