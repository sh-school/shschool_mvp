# تعيين PDPPL على مكوّنات SchoolOS

> المرجع: قانون قطر رقم (13) لسنة 2016 بإصدار قانون حماية خصوصية البيانات الشخصية، ولوائحه
> وإرشادات مكتب حماية البيانات الوطني (NDPO). هذا تعيين هندسي؛ النص القانوني هو المرجع النهائي.

## جدول التعيين

| مبدأ/مادة PDPPL | المتطلّب | المكوّن في SchoolOS |
|------------------|----------|---------------------|
| الموافقة (المعالجة تقوم على موافقة أو أساس مشروع) | تسجيل موافقة صريحة قابلة للسحب | `ConsentRecord` (`core/models/audit.py`) |
| حقوق صاحب البيان (وصول/تصحيح/اعتراض/محو) | آلية طلب ومعالجة | `ErasureRequest` + `api/views_erasure.py` |
| البيانات ذات الطبيعة الخاصة (الصحة، بيانات الأطفال، العِرق، الدين) | حماية مشدّدة + تقييد وصول + غالباً إذن الجهة المختصة | `clinic.HealthRecord` مشفّر بـ `EncryptedTextField`؛ RBAC صارم |
| ضمانات الأمن (سرّية/سلامة البيانات) | تشفير، تحكّم وصول، تسجيل | Fernet (`_crypto.py`)، `AuditLog`، `django-axes`، CSP، HSTS |
| إخطار الخرق | إبلاغ الجهة المختصة والمتأثرين خلال المدّة النظامية | `BreachReport` + تطبيق `breach/` |
| تقليل البيانات + تحديد الغرض | جمع الحدّ الأدنى للغرض المعلن | مراجعة `fields=[...]` في serializers؛ حقول «آمنة» بديلة |
| الشفافية | إشعار خصوصية واضح لصاحب البيان | صفحة/سياسة خصوصية + `ConsentRecord.purpose` |
| الشخص المسؤول عن الحماية | إشراف على الامتثال | دور القيادة + مراجعات هذا المدقّق |

## البيانات ذات الطبيعة الخاصة — أمثلة في المنصة
- صحية: `HealthRecord.allergies / chronic_diseases / medications / blood_type`.
- بيانات قُصّر: كل بيانات الطلاب (المنصة مدرسية → افتراض الحماية المشدّدة دائماً).
- معرّف رسمي: `national_id` (الرقم الشخصي القطري).

## نمط الحقل المشفّر — قبل/بعد

### ❌ قبل (تخزين صريح — مخالفة)
```python
class GuardianContact(models.Model):
    phone = models.CharField(max_length=20)          # PII صريح على القرص
    passport_no = models.CharField(max_length=30)    # وثيقة رسمية صريحة
```

### ✅ بعد (خيار 1 — الحقل المشفّر الشفّاف)
```python
from core.fields import EncryptedTextField

class GuardianContact(models.Model):
    phone = EncryptedTextField(blank=True)           # يُشفَّر/يُفكّ تلقائياً
    passport_no = EncryptedTextField(blank=True)
```

### ✅ بعد (خيار 2 — ثلاثية HMAC عند الحاجة للبحث)
كما في `core/models/user.py` للـ `national_id`:
```python
from core.models._crypto import encrypt_field, decrypt_field, hmac_field

class GuardianContact(models.Model):
    phone_encrypted = models.TextField(blank=True)   # القيمة المشفّرة (Fernet)
    phone_hmac = models.CharField(max_length=64, blank=True, db_index=True)  # للبحث

    def set_phone(self, value: str) -> None:
        self.phone_encrypted = encrypt_field(value)
        self.phone_hmac = hmac_field(value)          # ابحث عبر phone_hmac=hmac_field(q)

    @property
    def phone(self) -> str:
        return decrypt_field(self.phone_encrypted)
```
> التعبئة الأولية للبيانات القائمة تتم بأمر إدارة (مثل `populate_phone_encryption`) عبر ORM،
> لا بـ SQL خام، وإلا لن تمرّ عبر التشفير.

## تسريب serializer — قبل/بعد
```python
# ❌ يعرض PII للجميع
class ContactSerializer(ModelSerializer):
    class Meta: fields = ["id", "full_name", "national_id", "phone"]

# ✅ نسخة عامة آمنة + نسخة مقيّدة خلف permission
class ContactPublicSerializer(ModelSerializer):
    class Meta: fields = ["id", "full_name"]          # كـ UserSafeSerializer

class ContactPrivateSerializer(ModelSerializer):     # خلف IsTeacherOrAdmin
    class Meta: fields = ["id", "full_name", "national_id", "phone"]
```

## تسجيل آمن — قبل/بعد
```python
# ❌
logger.info(f"تحديث ولي أمر {guardian.national_id} هاتف {guardian.phone}")
# ✅
logger.info("تحديث ولي أمر id=%s", guardian.id)      # UUID فقط، لا PII
```

## المحو مقابل السجل القانوني
- امحُ/قيّد صفوف البيانات الشخصية عند طلب `ErasureRequest`.
- **أبقِ** `AuditLog` (سجل غير قابل للتعديل) — هو أساس مساءلة قانوني؛ قيّد الوصول إليه بدل حذفه.
- تحقّق من النسخ الاحتياطية والتقارير المولّدة: نطاق المحو يجب أن يشملها أو يوثّق استثناءها.
