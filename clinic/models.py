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
        "core.CustomUser",
        on_delete=models.CASCADE,
        related_name="health_record",
        verbose_name="الطالب",
    )
    # [W-029] العمودُ القديم `blood_type` بقي في القاعدة وحدها (مرحلة التوسيع):
    # لا حقلَ له هنا، فلا قراءةَ ولا كتابة. وهجرة 0011 جعلت له افتراضاً فارغاً
    # على مستوى القاعدة ليعمل النموذجُ القديمُ أثناء النشر المتدحرج. والحذفُ
    # الفعليّ طلبٌ منفصلٌ بعد استقرار الإصدار. ويمنع عودتَه حارسُ الاختبار.
    # القراءةُ والكتابةُ من هذا الحقل وحده. لا فلترةَ عليه (التشفير غير حتمي).
    blood_type_encrypted = EncryptedTextField(
        blank=True,
        default="",
        db_default="",
        choices=BLOOD_TYPES,
        verbose_name="فصيلة الدم",
    )
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
    emergency_contact_name = EncryptedTextField(blank=True, verbose_name="اسم جهة الطوارئ")
    emergency_contact_phone = EncryptedTextField(blank=True, verbose_name="هاتف جهة الطوارئ")
    # [W-028] سجلّ القيد الوزاريّ — ثلاثةُ أعمدةٍ صحّيّةٍ من ملف مركز البيانات
    # الوطنيّ، مشفَّرةٌ at-rest كبقيّة هذا النموذج (م.8 PDPPL). و`db_default`
    # لازمةٌ كحقل `blood_type_encrypted` أعلاه: الجدولُ فيه صفوفٌ بالفعل، فإضافةُ
    # عمودٍ بلا افتراضٍ على مستوى القاعدة تُسقط الهجرةَ (حارسُ migration-linter).
    health_center_name = EncryptedTextField(
        blank=True, default="", db_default="", verbose_name="اسم المركز الصحي الرئيسي"
    )
    health_card_number = EncryptedTextField(
        blank=True, default="", db_default="", verbose_name="رقم الرعاية الصحية الرئيسي"
    )
    hamad_hospital_number = EncryptedTextField(
        blank=True, default="", db_default="", verbose_name="رقم مستشفى حمد"
    )
    # [W-045، D-336م] علامةٌ محايدةٌ «يحتاج مراعاةً» يضعها الممرّض صراحةً وحده (لا تلقائيّاً من
    # أيّ تشخيص). منطقيٌّ غيرُ مشفَّر عمداً: لا يكشف سبباً، ويُستخرج برقم الطالب فقط
    # (`clinic.selectors.students_needing_care_ids`) دون فكّ أيّ حقلٍ مشفَّر. و`db_default`
    # لازمةٌ لأنّ الجدولَ فيه صفوفٌ (حارسُ migration-linter).
    needs_care = models.BooleanField(
        default=False,
        db_default=False,
        verbose_name="يحتاج مراعاةً",
        help_text="علامةٌ محايدةٌ تظهر للمعلّم في جدول رصد شعبته فقط، بلا سبب. يضعها الممرّض صراحةً.",
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التعديل")

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
    school = models.ForeignKey("core.School", on_delete=models.CASCADE, verbose_name="المدرسة")
    student = models.ForeignKey(
        "core.CustomUser",
        on_delete=models.CASCADE,
        related_name="clinic_visits",
        verbose_name="الطالب",
    )
    nurse = models.ForeignKey(
        "core.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        related_name="nurse_visits",
        verbose_name="الممرّض",
    )
    visit_date = models.DateTimeField(auto_now_add=True, verbose_name="وقت الزيارة")
    # بيانات صحية حسّاسة (م.8 PDPPL) — مشفّرة at-rest بـ Fernet
    reason = EncryptedTextField(verbose_name="سبب الزيارة")
    symptoms = EncryptedTextField(blank=True, verbose_name="الأعراض")
    temperature = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True, verbose_name="درجة الحرارة"
    )
    treatment = EncryptedTextField(blank=True, verbose_name="الإجراء المتخذ")
    is_sent_home = models.BooleanField(default=False, verbose_name="تم إرساله للمنزل")
    parent_notified = models.BooleanField(default=False, verbose_name="تم إبلاغ ولي الأمر")

    # ── [W-20261020-029] ترميز الزيارة ───────────────────────────────────
    # رموزٌ من القوائم المغلقة في `clinic/choices.py` (بلا `choices` هنا عمداً: تعديلُ قائمةٍ
    # قيماً لا يولّد هجرةً)، وكلُّها غيرُ مشفَّرٍ لأنّها قيمٌ مصنَّفةٌ بلا نصٍّ حرّ ولا تشخيص؛
    # والنصُّ الحرُّ (reason/symptoms/treatment) يبقى مشفَّراً للممرّض وخارجَ كلّ تجميع.
    # `db_default` لازمةٌ لأنّ الجدولَ فيه صفوف (حارسُ migration-linter).
    service_code = models.CharField(
        max_length=40, blank=True, default="", db_default="", verbose_name="الخدمة"
    )
    service_group = models.CharField(
        max_length=20, blank=True, default="", db_default="", verbose_name="مجموعة الخدمة"
    )
    complaint_code = models.CharField(
        max_length=40, blank=True, default="", db_default="", verbose_name="الشكوى"
    )
    outcome = models.CharField(
        max_length=20, blank=True, default="", db_default="", verbose_name="حالة الخروج"
    )
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت إغلاق الزيارة")
    period_number = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="رقم الحصة (مشتقّ)",
        help_text="يُشتقّ من الجدول قراءةً فقط عند التسجيل؛ لا يُدخله الممرّض.",
    )

    class Meta:
        verbose_name = "زيارة عيادة"
        verbose_name_plural = "زيارات العيادة"
        ordering = ["-visit_date"]
        db_table = "core_clinicvisit"  # يبقي نفس الجدول الموجود

    @property
    def duration_seconds(self) -> int | None:
        """مدّةُ المكث بالثواني من البدء حتى الإغلاق؛ None لزيارةٍ مفتوحة."""
        if self.closed_at is None or self.visit_date is None:
            return None
        return max(0, int((self.closed_at - self.visit_date).total_seconds()))

    #: حرارةٌ تُعدّ حُمّى — كانت عتبةً مكتوبةً في قالب سجلّ الزيارات (≥ 38).
    FEVER_THRESHOLD = 38

    def __str__(self):
        return f"Visit: {self.student.full_name} - {self.visit_date.date()}"

    @property
    def is_feverish(self) -> bool:
        return self.temperature is not None and self.temperature >= self.FEVER_THRESHOLD


# ── [W-20261020-036] صرف الدواء: كتالوجٌ معتمَدٌ وموافقةُ وليّ الأمر ─────────────────
# لا صرفَ من نصٍّ حرّ: الصرفُ سطرٌ يربط زيارةً ببندٍ من كتالوجٍ اعتمدته جهةٌ طبّيّة، وبموافقةٍ سارية لوليّ أمر
# الطالب. وكلُّ ما هنا قيمٌ مصنَّفةٌ بلا نصٍّ حرّ ولا تشخيص (كأعمدة الترميز في `ClinicVisit`)، فلا يلزمها التشفير؛
# والنصُّ الحرُّ الصحّيّ يبقى مشفَّراً في مكانه. والقواعدُ في `clinic/medication_services.py` لا هنا.


class MedicationCatalogItem(models.Model):
    """بندٌ في كتالوج الأدوية المعتمَد سريرياً للمدرسة — لا يُصرف دواءٌ خارجه."""

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        "core.School",
        on_delete=models.PROTECT,
        related_name="medication_catalog",
        verbose_name="المدرسة",
    )
    name = models.CharField(max_length=120, verbose_name="اسم الدواء")
    standard_dose = models.CharField(max_length=80, verbose_name="الجرعة المعتمَدة")
    is_active = models.BooleanField(default=True, verbose_name="مفعَّل")
    approved_by = models.ForeignKey(
        "core.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="اعتمده",
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="وقت الاعتماد السريري",
        help_text="فارغٌ = لم يُعتمد بعدُ فلا يُصرف.",
    )

    class Meta:
        verbose_name = "دواءٌ في الكتالوج"
        verbose_name_plural = "كتالوج الأدوية المعتمَد"
        constraints = [
            models.UniqueConstraint(fields=["school", "name"], name="uniq_medication_per_school")
        ]
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} — {self.standard_dose}"

    @property
    def is_dispensable(self) -> bool:
        """يُصرف إن كان مفعَّلاً ومعتمَداً سريرياً."""
        return self.is_active and self.approved_at is not None


class GuardianMedicationConsent(models.Model):
    """موافقةُ وليّ الأمر على صرف بندٍ من الكتالوج لطالبه — مدّتُها محدودة وتُسحَب."""

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey("core.School", on_delete=models.PROTECT, verbose_name="المدرسة")
    student = models.ForeignKey(
        "core.CustomUser",
        on_delete=models.CASCADE,
        related_name="medication_consents",
        verbose_name="الطالب",
    )
    catalog_item = models.ForeignKey(
        MedicationCatalogItem,
        on_delete=models.PROTECT,
        related_name="consents",
        verbose_name="الدواء",
    )
    granted_at = models.DateTimeField(verbose_name="وقت الموافقة")
    expires_at = models.DateTimeField(verbose_name="ينتهي في")
    revoked_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت السحب")
    recorded_by = models.ForeignKey(
        "core.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="سجّلها",
    )

    class Meta:
        verbose_name = "موافقة وليّ أمر على دواء"
        verbose_name_plural = "موافقات أولياء الأمور على الأدوية"
        constraints = [
            models.CheckConstraint(  # type: ignore[call-arg]  # Django 5.1+: condition
                condition=models.Q(expires_at__gt=models.F("granted_at")),
                name="medication_consent_expires_after_grant",
            )
        ]
        indexes = [models.Index(fields=["student", "catalog_item"])]

    def __str__(self) -> str:
        return f"موافقة {self.pk}"


class VisitMedication(models.Model):
    """صرفُ دواءٍ في زيارة: بندُ كتالوجٍ وجرعتُه المعتمَدة والموافقةُ التي استند إليها. لا نصَّ حرّاً."""

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey("core.School", on_delete=models.PROTECT, verbose_name="المدرسة")
    visit = models.ForeignKey(
        ClinicVisit,
        on_delete=models.CASCADE,
        related_name="medications",
        verbose_name="الزيارة",
    )
    catalog_item = models.ForeignKey(
        MedicationCatalogItem,
        on_delete=models.PROTECT,
        related_name="dispensings",
        verbose_name="الدواء",
    )
    dose = models.CharField(
        max_length=80,
        verbose_name="الجرعة المصروفة",
        help_text="نسخةٌ من الجرعة المعتمَدة وقتَ الصرف، فتعديلُ الكتالوج لاحقاً لا يغيّر ما صُرف.",
    )
    consent = models.ForeignKey(
        GuardianMedicationConsent,
        on_delete=models.PROTECT,
        related_name="dispensings",
        verbose_name="الموافقة المستند إليها",
    )
    dispensed_by = models.ForeignKey(
        "core.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        verbose_name="صرفه",
    )
    dispensed_at = models.DateTimeField(verbose_name="وقت الصرف")

    class Meta:
        verbose_name = "صرف دواء"
        verbose_name_plural = "صرف الأدوية"
        ordering = ["-dispensed_at"]

    def __str__(self) -> str:
        return f"صرف {self.pk}"
