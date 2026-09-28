# أنماطُ الإصلاح — قبل وبعد

متى تقرأ هذا الملف: حين تكتب الإصلاحَ فعلاً — حقلٌ يُشفَّر، مُسلسِلٌ يُقلَّص، سطرُ تسجيلٍ يُنظَّف، نموذجٌ يدخل المحو، أو مُصدِّرٌ يُدقَّق. الأمثلةُ بأسماءٍ مختلَقة.

## 1. حقلٌ شخصيٌّ جديد

### خطأ: تخزينٌ صريح
```python
class GuardianContact(models.Model):
    phone = models.CharField(max_length=20)
    passport_no = models.CharField(max_length=30)
```

### الصواب: لا يُبحث به: الحقلُ الشفّاف
```python
from core.fields import EncryptedTextField

class GuardianContact(models.Model):
    phone = EncryptedTextField(blank=True, verbose_name="الجوال")
    passport_no = EncryptedTextField(blank=True, verbose_name="رقم الجواز")
```
- الحقلُ `TextField` في القاعدة: التحويلُ من `CharField` هجرةٌ تغيّر النوع — تمرّ على مهارة `schoolos-migration-guard` وقاعدة «توسيعٌ ثمّ تقليص» في `CLAUDE.md`.
- القيمُ القديمة تُشفَّر بأمر إدارةٍ عبر ORM (نمطُ `populate_phone_encryption`)، لا `UPDATE` خام — الخامُ لا يمرّ بالتشفير.
- `verbose_name` عربيٌّ إلزاميّ (`tests/test_model_field_labels_arabic.py`).

### الصواب: يُبحث به أو يلزم تفرّدُه: الثلاثيّة
```python
from core.models.crypto import encrypt_field, hmac_field

class GuardianContact(models.Model):
    phone_encrypted = models.TextField(blank=True, default="", verbose_name="الجوال (مشفّر)")
    phone_hmac = models.CharField(max_length=64, blank=True, default="", db_index=True, verbose_name="HMAC الجوال")

    def set_phone(self, value: str) -> None:
        self.phone_encrypted = encrypt_field(value)
        self.phone_hmac = hmac_field(value)

# البحث: GuardianContact.objects.filter(phone_hmac=hmac_field(q))
```
- `core/models/user.py` يُبقي الخامَ أيضاً لأنّ `national_id` اسمُ الدخول؛ نموذجٌ جديدٌ لا يحتاج خاماً.
- `hmac_field` يقصّ المسافات قبل الحساب — طبّع المُدخَلَ بالطريقة نفسها عند الحفظ والبحث.

## 2. مُسلسِلٌ يعرض أشخاصاً
```python
# خطأ:
class ContactSerializer(ModelSerializer):
    class Meta:
        model = GuardianContact
        fields = "__all__"

# الصواب: عامّ: الاسمُ وحده (على مثال UserSafeSerializer)
class ContactPublicSerializer(ModelSerializer):
    class Meta:
        model = GuardianContact
        fields = ["id", "full_name"]

# الصواب: مقيَّد: يحذف ويستر حسب الطالب (على مثال UserBriefSerializer.to_representation)
class ContactPrivateSerializer(ModelSerializer):
    class Meta:
        model = GuardianContact
        fields = ["id", "full_name", "national_id"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        from core.privacy import mask_national_id
        data["national_id"] = mask_national_id(data.get("national_id"))
        return data
```
والإذنُ على الـview لا على المُسلسِل وحده (`api/permissions.py`: `IsTeacherOrAdmin`، `IsSchoolAdmin`، `IsParentOrAdmin`…)، والنطاقُ بالمدرسة (RLS و`get_school()`).

## 3. قالبُ قائمة
```django
{% load privacy %}
{% for s in students %}
  <td>{{ s.full_name }}</td>
  <td>{{ s.national_id|mask_id }}</td>   {# خطأ: {{ s.national_id }} يُسقط الحارس #}
{% endfor %}
```

## 4. سطرُ تسجيل
```python
# خطأ: (نمطٌ موجودٌ اليوم في student_affairs/services.py)
logger.info("تم إنشاء طالب: %s (national_id=%s)", user.full_name, national_id)
# الصواب:
logger.info("تم إنشاء طالب id=%s في المدرسة %s", user.pk, school.code)
```
ولا `str(exc)` يُعاد للمستخدم أو يُخزَّن إن كان الاستثناءُ قد يحمل قيمةً (نمطُ `core/exports/messages.py`: رموزٌ ثابتة).

## 5. نموذجٌ جديدٌ يحمل الطالب
```python
class CounselingNote(models.Model):          # مثالٌ مختلَق
    student = models.ForeignKey("core.CustomUser", on_delete=models.CASCADE, related_name="counseling_notes")
    body = EncryptedTextField(verbose_name="المحتوى")   # نفسيّ ⇒ ذو طبيعةٍ خاصّة (م.16)
    attachment = models.FileField(blank=True)
```
المطلوبُ معه في الطلب نفسه:
1. سطرٌ في `governance/erasure_service.py::_lazy_student_fk_models` وآخرُ في `_lazy_file_field_models` للمرفق.
2. `clean_photo` على المرفق إن قبل صوراً.
3. بندٌ في `AuditLog.MODEL_CHOICES` إن كان يُعرض أو يُصدَّر ويُدقَّق.
4. سؤالُ الـDPO عن تصريح م.16 قبل النشر.

## 6. مُصدِّرٌ جديد
```python
from core.audit_export import log_export
log_export(request, "counseling.notes_pdf", rows=len(rows), object_id=class_grp.pk,
           object_repr=f"ملاحظات {class_grp}")   # لا اسمَ طالبٍ ولا رقم
```
والأفضل بنّاءٌ في سجلّ التصدير (`core/exports/registry.py`) — التفصيل في `schoolos-report-ar`.

## 7. المحوُ مقابل السجلّ القانونيّ
- يُجهَّل صفُّ الطالب وتوابعُه وتُحذف ملفّاتُه؛ `AuditLog` يبقى بفصل الهويّة (`update(user=None)` هو التعديلُ الوحيد المسموح).
- النسخُ الاحتياطيّة: ما يُحذف من القاعدة يزول من آخر نسخةٍ بعد دورة حياتها (400 يوم في `docs/privacy/data_retention.md`، مضبوطةٌ خارج المستودع) — اذكر ذلك في ردّ طلب المحو لا تَعِد بمحوٍ فوريٍّ منها.

## أنماطٌ مضادّة
- `filter(phone=q)` على حقلٍ مشفَّر، أو حفظُ HMAC دون تطبيعٍ موحَّد.
- إصلاحُ السجلّ بستر الرقم وترك الاسم.
- ستر الرقم في القالب مع إرساله كاملاً في JSON للصفحة نفسها.
- إضافةُ نموذجٍ صحّيٍّ أو نفسيٍّ دون سؤال الـDPO، أو دون مكانٍ في المحو.
