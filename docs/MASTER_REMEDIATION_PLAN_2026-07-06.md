# الخطة الرئيسية للإصلاح — منصة SchoolOS
### تقرير موحّد (التدقيق العدائي + SWOT) + خطة إصلاح كاملة قابلة للتنفيذ

**التاريخ:** 2026-07-06 · **المسار:** `D:\shschool_mvp` (فرع main) · **الحالة:** خطة تنفيذ
**المصادر المدموجة:** التدقيق العدائي عبر مهارات SchoolOS (`docs/AUDIT_REPORT_2026-07-06.md`) +
تقرير SWOT التشريحي (`docs/schoolos_swot_deep_report_2026-07-06.html`)
**الهدف الكمّي:** رفع التقييم المركّب من **75/100** إلى **90+/100** خلال نافذة 90 يوماً، وإغلاق كل بنود P0.

> **قاعدة التنفيذ:** كل التعديلات على `D:\shschool_mvp` مباشرة. بعد تعديل CSS/JS شغّل `collectstatic`
> وارفع رقم الإصدار. كل إصلاح يُرافقه اختبار يمنع ارتداده.

---

## 1. الملخّص التنفيذي الموحّد

المنصة **ناضجة هندسياً** (تشفير fail-closed، عزل مستأجرين ثلاثي، دورة PDPPL كاملة، Celery، تدقيق
غير قابل للتعديل، `transaction.atomic` في 90 موضعاً). الفجوات **نقطية محدّدة الموقع** ولا تتطلب إعادة تصميم.
التقريران متكاملان: التدقيق العدائي أعمق في **الخصوصية القابلة للاستغلال والأداء**، وSWOT أعمق في
**الموثوقية التشغيلية والحوكمة**. بعد التحقّق المصدري، دُمجت النتائج وحُسمت التناقضات.

### الحصيلة الموحّدة بعد إزالة التكرار

| الخطورة | العدد | أبرز البنود |
|---------|:---:|-------------|
| 🔴 حرجة | 8 | rotate_fernet_key مكسور · national_id في AuditLog · شلال حساب الدرجات · RLS fail-open · هشاشة التشفير · PDF/إشعارات متزامنة |
| 🟠 عالية | 18 | تسريب PII في serializers · محو ناقص · DLQ مفقود · denormalization · IDOR وصول المعلم · N+1 التقارير |
| 🟡 متوسطة | 22 | فهارس · caching KPIs · حقول حسّاسة صريحة · JWT blacklist · بوابة التغطية |
| ⚪ منخفضة | 10 | تصلّب CSRF · ملفات يتيمة · سجلّات مؤقّتة |
| **الإجمالي** | **58** | |

### أخطر 8 بنود (P0) — يجب إغلاقها أولاً

| # | البند | المصدر | لماذا P0 |
|---|------|--------|----------|
| P0-1 | `rotate_fernet_key` مكسور يُتلف البيانات الصحية والهواتف بصمت | التدقيق | فقد بيانات لا رجعة فيه عند أول تدوير مفتاح |
| P0-2 | `national_id` الخام في `AuditLog` يَنجو من المحو (م.18/م.19) | التدقيق | خرق PDPPL — المحو غير مكتمل قانونياً |
| P0-3 | شلال حساب/حفظ الدرجات: 300–600 استعلام + 90 قفلاً/طلب | التدقيق | حجب worker + خطر timeout على كل حفظ درجات فصل |
| P0-4 | RLS fail-open عند فشل ضبط السياق | كلاهما | تسرّب بيانات عبر المدارس |
| P0-5 | هشاشة التشفير: فشل `save()` قد يترك PII صريحاً | كلاهما | تسريب PII صامت |
| P0-6 | توليد PDF/Excel والإشعارات الجماعية متزامناً | التدقيق | حجب الطلب + انهيار تحت الحمل |
| P0-7 | المحو لا يصفّر أعمدة `_encrypted`/`_hmac` | التدقيق | استرجاع الرقم الشخصي/الهاتف بعد «المحو» |
| P0-8 | لا Dead-Letter Queue + دفع WebSocket fail-silent | SWOT | فقد إشعارات حرجة (غياب/رسوب) بصمت |

---

## 2. سجل النتائج الموحّد (Findings Register)

المصدر: **A** = التدقيق العدائي، **S** = SWOT، **A+S** = كلاهما (تحقّق مزدوج).

### 2.1 الأمن (Security / OWASP / Zero-Trust)
| مُعرّف | النتيجة | خطورة | مصدر | الموقع |
|------|---------|:---:|:---:|--------|
| SEC-01 | RLS fail-open عند فشل ضبط السياق | 🔴 | A+S | `core/middleware_rls.py:66-67` |
| SEC-02 | تدوير refresh token دون قائمة حظر | 🟡 | A | `settings/base.py:350-353` |
| SEC-03 | صلاحيات تسمح افتراضياً عند غياب المعرّف | 🟡 | A | `api/permissions.py:99,138` |
| SEC-04 | وصول المعلم واسع في تصدير التقارير (غير مقيّد بفصله) | 🟠 | S | `reports/views.py:106-137` |
| SEC-05 | `CSRF_COOKIE_HTTPONLY=False` | 🟡 | A | `settings/base.py:280` |
| SEC-06 | رفع ملف مموّه (فحص الامتداد لا المحتوى) | 🟡 | S | `operations/models.py` |
| SEC-07 | كلمة مرور الاستيراد = الرقم الشخصي | ⚪ | A | `import_students_parents.py` |

### 2.2 الخصوصية (PDPPL / PII)
| مُعرّف | النتيجة | خطورة | مصدر | الموقع |
|------|---------|:---:|:---:|--------|
| PII-01 | `rotate_fernet_key` مكسور (حقول خاطئة، ClinicVisit/الهاتف مُهمَلان) | 🔴 | A | `management/commands/rotate_fernet_key.py:47,77` |
| PII-02 | `national_id` خام في `AuditLog.changes` و`object_repr` | 🔴 | A | `core/signals.py:239` · `user.py:110` |
| PII-03 | `UserBriefSerializer` يكشف national_id+phone لكل معلم | 🟠 | A | `api/serializers.py:47-52` |
| PII-04 | `emergency_contact_*` نصّ صريح | 🟠 | A | `clinic/models.py:41-42` |
| PII-05 | `ClinicVisitSerializer` يعرض المحتوى الطبي بلا نسخة آمنة | 🟠 | A | `api/serializers.py:374-390` |
| PII-06 | حقول سلوك/أمنية لقُصّر نصّ صريح | 🟠 | A | `behavior/models.py:292+` |
| PII-07 | المحو لا يصفّر `_encrypted`/`_hmac` | 🟠 | A | `core/erasure_service.py:164-173` |
| PII-08 | `national_id` في اسم ملف PDF | 🟡 | A | `behavior/views.py:851` |
| PII-09 | بيانات السائقين + `gps_link` صريحة | 🟡 | A | `transport/models.py:26-37` |
| PII-10 | `EncryptedTextField` fail-open صامت | 🟡 | A+S | `core/fields.py:20-21` |
| PII-11 | تسجيل بريد ولي الأمر | 🟡 | A | `behavior/views.py:497` |
| PII-13 | الموافقة موثّقة لا مفروضة تقنياً | 🟡 | A | `clinic/services.py` |

### 2.3 الأداء (Performance / N+1 / Celery)
| مُعرّف | النتيجة | خطورة | مصدر | الموقع |
|------|---------|:---:|:---:|--------|
| PERF-01 | `recalculate_full_class` تسلسلي متداخل | 🔴 | A | `assessments/services.py:370-379` |
| PERF-02 | `save_all_grades` إعادة حساب لكل طالب داخل POST | 🔴 | A | `assessments/views.py:333-378` |
| PERF-03 | توليد PDF كشوف/شهادات داخل الطلب | 🔴 | A | `reports/views.py:132-181` |
| PERF-04 | `get_exam_results_reports` استعلام لكل باقة | 🔴 | A | `reports/services.py:454-467` |
| PERF-05 | إشعارات جماعية متزامنة من الـ view | 🔴 | A | `notifications/views.py:63-88` |
| PERF-06→14 | تصدير Excel متزامن، N+1 في قوالب النقل/البدلاء/السلوك/exam/التقرير اليومي | 🟠 | A | (تفصيل في تقرير التدقيق) |
| PERF-15→24 | دمج `filter().count()`، caching KPIs، فهارس مركّبة، `student_count` annotate | 🟡 | A | متعدّد |

### 2.4 الموثوقية والمعمارية (Reliability / Architecture / Data)
| مُعرّف | النتيجة | خطورة | مصدر | الموقع |
|------|---------|:---:|:---:|--------|
| REL-01 | لا Dead-Letter Queue + دفع WebSocket fail-silent | 🟠 | S | `notifications/hub.py:178` · `tasks.py` |
| ARCH-01 | Denormalization: `level` من `category.degree` عند كل حفظ | 🟠 | S+A✓ | `behavior/models.py:410-411` |
| ARCH-02 | الكتابة الجماعية للدرجات ليست idempotent-batch | 🟠 | A | `assessments/services.py` |
| REL-02 | ملفات excuse يتيمة (UUID بلا ربط) | 🟡 | S | `operations/models.py:15-18` |
| REL-03 | FSM الخرق يسمح rollback (notified→assessing) | 🟡 | S | `breach/` |
| GOV-01 | تعارض/تضليل بوابة التغطية عبر الـ workflows | 🟡 | S+A✓ | `.github/workflows/*` |
| ARCH-03 | تغطية اختبارات ≈63% دون هدف 85% | 🟡 | A+S | `pyproject.toml:100` |
| GOV-02 | سرعة ثغرات الاعتماديات (مخفَّفة بـ pip-audit) | ⚪ | S | `ci.yml:264` |

---

## 3. خطة الإصلاح المرحلية

ثلاث مراحل: **P0 (أسبوعان)** حرجة → **P1 (سبرنت)** عالية → **P2 (سبرنت تالٍ)** متوسطة/تصلّب.
كل بند: المشكلة → السبب الجذري → الإصلاح الملموس → الجهد → المسؤول → معيار القبول.

---

## 4. المرحلة P0 — حرجة (الأسبوعان 1–2)

### P0-1 · إصلاح `rotate_fernet_key` [PII-01]
**السبب الجذري:** تعداد يدوي لأسماء الحقول أخطأ (`_allergies` بدل `allergies`)، وأهمل `ClinicVisit` و`phone_encrypted`.
**الإصلاح:** سجل مركزي للحقول المشفّرة + إعادة تشفير عبر ORM (يمرّ تلقائياً بالمفتاح الحالي).

```python
# core/crypto_registry.py (جديد — مصدر حقيقة واحد)
ENCRYPTED_FIELDS = {
    "clinic.ClinicVisit":  ["reason", "symptoms", "treatment"],      # EncryptedTextField
    "clinic.HealthRecord": ["allergies", "chronic_diseases", "medications"],  # get/set يدوي
    "core.CustomUser":     ["national_id", "phone"],                 # ثلاثية HMAC
}

# core/management/commands/rotate_fernet_key.py (مُعاد)
from django.apps import apps
from core.crypto_registry import ENCRYPTED_FIELDS

def handle(self, *args, **opts):
    for dotted, fields in ENCRYPTED_FIELDS.items():
        Model = apps.get_model(dotted)
        for obj in Model.objects.all().iterator(chunk_size=500):
            # القراءة تفكّ بالمفتاح القديم (MultiFernet) والحفظ يشفّر بالحالي
            obj.save(update_fields=[*_encrypted_columns(Model, fields), "updated_at"])
```
> `EncryptedTextField`: `.save()` يكفي. `HealthRecord`/`CustomUser`: استدعِ `set_x()`/أعِد ضبط الحقل الخام
> ليُعاد حساب `_encrypted`+`_hmac` في `save()`. **اختبر على نسخة إنتاج قبل إزالة المفتاح القديم.**

**الجهد:** 4–5 س · **المسؤول:** Backend + Security · **القبول:** أمر إدارة `verify_encryption` يؤكّد
فكّ كل الحقول بالمفتاح الجديد بعد إزالة القديم؛ اختبار يشمل ClinicVisit والهاتف والصحة.

### P0-2 · إزالة `national_id` الخام من التدقيق [PII-02]
**السبب:** `AuditLog.object_repr = str(user)` و`changes` يخزّنان الرقم الشخصي خاماً في جدول دائم.
```python
# core/models/user.py
def __str__(self):
    return self.full_name                         # بلا رقم شخصي

# core/signals.py — عند تدقيق مستخدم
changes = {"action": "create", "user_id": str(instance.id)}   # UUID فقط، لا national_id
audit_object_repr = instance.full_name            # أو f"user:{instance.id}"
```
**الجهد:** 2–3 س · **المسؤول:** Backend + Security · **القبول:** مسح `AuditLog` لا يُظهر أي رقم شخصي؛
اختبار يتحقّق أن إنشاء مستخدم لا يكتب `national_id` في `changes`/`object_repr`.

### P0-3 · إعادة صياغة حساب/حفظ الدرجات [PERF-01/02 · ARCH-02]
**السبب:** إعادة حساب لكل طالب داخل POST بدل batch (الأداة `calc_package_scores_batch` موجودة وغير مستخدمة).
```python
# assessments/services.py
@staticmethod
@transaction.atomic
def save_class_grades_batch(setup, class_group, semester, grades: dict):
    # 1) حفظ الدرجات الخام دفعةً واحدة
    objs = [StudentAssessmentGrade(...) for sid, g in grades.items()]
    StudentAssessmentGrade.objects.bulk_create(objs, update_conflicts=True,
        unique_fields=[...], update_fields=["grade"])
    # 2) حساب نتائج الباقات لكل الطلاب باستعلام واحد
    scores = GradeService.calc_package_scores_batch(setup, list(grades), semester)
    StudentSubjectResult.objects.bulk_update(_build(scores), ["score", "is_pass"])
    # 3) نتيجة سنوية batch واحدة (لا حلقة لكل طالب)

# نقل الطلب الثقيل إلى Celery
@shared_task
def recalc_class_task(class_id, year): ...
```
**الجهد:** 8–10 س · **المسؤول:** Backend · **القبول:** `django_assert_num_queries` يثبت عدداً **ثابتاً**
مهما زاد الطلاب؛ زمن الاستجابة < 300ms (الباقي في Celery).

### P0-4 · RLS fail-closed [SEC-01]
```python
# core/middleware_rls.py
from django.db import OperationalError, DatabaseError
def _apply(self, value):
    try:
        with connection.cursor() as c:
            c.execute("SELECT set_config('app.current_school_id', %s, false)", [value])
    except (OperationalError, DatabaseError) as e:
        logger.error("RLS set failed — رفض الطلب (fail-closed): %s", e)
        raise                                     # لا تتابع بسياق موروث

def __call__(self, request):
    try:
        self._apply(self._context(request))
    except (OperationalError, DatabaseError):
        from django.http import HttpResponse
        return HttpResponse("الخدمة غير متاحة مؤقتاً", status=503)
    try:
        return self.get_response(request)
    finally:
        self._apply("")
```
**الجهد:** 3–4 س · **المسؤول:** Backend + DB · **القبول:** اختبار ضغط (concurrency) يثبت صفر تسرّب سياق؛
محاكاة فشل `set_config` تُعيد 503 لا بيانات.

### P0-5 · صلابة التشفير (fail-closed على الحفظ) [PII-10 · SEC/A+S]
```python
# core/fields.py
def get_prep_value(self, value):
    value = super().get_prep_value(value)
    if value in (None, ""):
        return value
    enc = encrypt_field(str(value))
    if enc == str(value):                          # fail-open أرجع الأصل ⇒ فشل تشفير
        raise ImproperlyConfigured("فشل تشفير حقل حسّاس — رُفض الحفظ (fail-closed)")
    return enc
```
+ فحص دوري (أمر إدارة) يكشف أي حقل حسّاس نصّ صريح، ويُربط بالـ CI.
**الجهد:** 4–5 س · **المسؤول:** Backend + Security · **القبول:** محاولة حفظ بمفتاح فاسد تُرفَض؛ فحص دوري = صفر حقول صريحة.

### P0-6 · نقل التوليد الثقيل إلى Celery [PERF-03/05/06]
```python
# reports/tasks.py (النمط مطبَّق أصلاً في analytics/tasks.py)
@shared_task
def build_class_certificates_pdf(class_id, year, user_id):
    ...  # جلب batch لبيانات الطلاب (لا حلقة get_student_report) ثم render_pdf
    # خزّن الملف + أرسل إشعار "جاهز للتنزيل"

# reports/views.py — الـ view يُطلق المهمة ويعيد 202 + معرّف
task = build_class_certificates_pdf.delay(class_id, year, request.user.id)
return JsonResponse({"job_id": task.id}, status=202)
```
وبالمثل تغليف تنسيق الإشعارات الجماعية (`send_pending_absence_alerts`) في `@shared_task`.
**الجهد:** 6–8 س · **المسؤول:** Backend + DevOps · **القبول:** لا عملية توليد/إرسال تتجاوز 300ms في دورة الطلب.

### P0-7 · إكمال المحو للأعمدة المشفّرة [PII-07]
```python
# core/erasure_service.py — قبل student.save()
student.national_id_encrypted = ""
student.national_id_hmac = ""
student.phone_encrypted = ""
student.phone_hmac = ""
```
**الجهد:** 1 س · **المسؤول:** Backend · **القبول:** بعد المحو، `decrypt_field` على الصف لا يُرجع القيمة الأصلية؛ اختبار يثبت تصفير الأعمدة الأربعة.

### P0-8 · Dead-Letter Queue للإشعارات [REL-01]
```python
# notifications/models.py
class DeadLetterMessage(TimeStampedModel):
    kind = models.CharField(max_length=20)        # email|sms|push
    payload = models.JSONField()
    error = models.TextField()
    resolved = models.BooleanField(default=False)

# notifications/tasks.py
@shared_task(bind=True, max_retries=3, acks_late=True)
def send_email_task(self, ...):
    try: ...
    except (OSError, RuntimeError, ValueError) as exc:
        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError:
            DeadLetterMessage.objects.create(kind="email", payload=..., error=str(exc))
```
+ إنهاء fail-silent للأحداث الحرجة في `hub.py:178` (سجّل + عدّاد + تنبيه عند تجاوز عتبة).
**الجهد:** 6–7 س · **المسؤول:** Backend + DevOps · **القبول:** رسالة فاشلة تنتهي في DLQ لا في العدم؛ لوحة/تنبيه عند تراكم > 5/يوم.

---

## 5. المرحلة P1 — عالية (الأسبوع 3–6)

### P1-1 · تقييد وصول المعلم بفصله في التقارير [SEC-04]
المعلم حالياً يصدّر أي فصل بمدرسته (مقيّد بالمدرسة لا بالفصل). أضِف فحص تدريس:
```python
# reports/views.py — داخل class_results_pdf ونظائرها
from django.core.exceptions import PermissionDenied
if not (request.user.is_admin() or SubjectClassAssignment.objects.filter(
        teacher=request.user, class_group=class_grp).exists()):
    raise PermissionDenied("لا تدرّس هذا الفصل")
```
**الجهد:** 4–5 س · **Backend + Security** · **القبول:** اختبار: معلم فصل A يُمنع (403) من تقرير فصل B بنفس المدرسة.

### P1-2 · فصل serializers الحساسة [PII-03/05]
```python
class StudentListItemSerializer(ModelSerializer):
    class Meta: model = CustomUser; fields = ["id", "full_name"]   # القوائم العامة
# UserBriefSerializer (national_id/phone) → عبر get_serializer_class لشؤون الطلبة/القيادة فقط
# ClinicVisitMetaSerializer (تاريخ/أُرسل للمنزل) ⟂ ClinicVisitMedicalSerializer (طبي، للممرّض/القيادة)
```
**الجهد:** 4–5 س · **Backend** · **القبول:** اختبار: معلم لا يرى national_id/phone/محتوى طبي عبر القوائم.

### P1-3 · تشفير الحقول الحسّاسة المتبقّية [PII-04/06/09]
حوّل إلى `EncryptedTextField` (أو ثلاثية عند الحاجة للبحث):
`clinic.emergency_contact_name/phone` · `behavior.violation_description/digital_evidence_notes/security_notes` ·
`transport.driver_phone`. الترحيل عبر أمر إدارة (ORM، لا SQL خام) — استخدم `schoolos-migration-guard`.
**الجهد:** 6–8 س · **Backend + Security** · **القبول:** `pii_scan.py` = صفر حقول حسّاسة صريحة في هذه النماذج.

### P1-4 · تجميد الدرجة عند الإنشاء (Denormalization) [ARCH-01]
```python
# behavior/models.py
def save(self, *args, **kwargs):
    if self._state.adding and self.violation_category and self.violation_category.degree:
        self.level = self.violation_category.degree     # فقط عند الإنشاء لا كل حفظ
    super().save(*args, **kwargs)
```
+ أداة تصحيح تاريخي اختيارية. **الجهد:** 5–6 س · **Backend** · **القبول:** تعديل فئة لا يغيّر `level` لمخالفات قديمة؛ اختبار تاريخي.

### P1-5 · إزالة N+1 من التقارير والقوالب [PERF-04/06-14]
- `get_exam_results_reports`: اجلب كل `StudentSubjectResult` للـ setups دفعةً بخريطة `(setup,semester)→[results]`.
- طبّق `with_details()`/`with_student()`/`select_related` الموجودة على قوالب النقل/البدلاء/السلوك/exam_control/التقرير اليومي.
- استبدل `{{ x.count }}` بـ `annotate(Count(...))`؛ `ClassGroupSerializer.get_student_count` → annotate في الـ view.
**الجهد:** 8–10 س · **Backend** · **القبول:** `nplus1_scan.py` نظيف على هذه الشاشات + `django_assert_num_queries` ثابت.

### P1-6 · قائمة حظر refresh tokens [SEC-02]
```python
INSTALLED_APPS += ["rest_framework_simplejwt.token_blacklist"]
SIMPLE_JWT["BLACKLIST_AFTER_ROTATION"] = True
```
+ إبطال عند الخروج. **الجهد:** 2–3 س · **Backend** · **القبول:** refresh token مُدوَّر/خروج = مرفوض فوراً.

### P1-7 · توحيد بوابة التغطية [GOV-01]
الواقع: `ci.yml` السريع يفرض `--cov-fail-under=0` عمداً، `nightly.yml=60`، `quality-gate.yml` يُسمّى «≥85».
وحّد: `pyproject.toml` مصدر واحد للعتبة؛ صحّح أسماء الوظائف لتعكس الواقع (fast=بلا بوابة، nightly=البوابة الفعلية)؛
خارطة رفع 63%→70%→80%→85%. **الجهد:** 2–3 س · **QA** · **القبول:** لا اسم وظيفة يناقض عتبته.

### P1-8 · FSM للخرق (منع rollback غير القانوني) [REL-03]
حوّل انتقالات `BreachReport.status` إلى آلة حالة صريحة تمنع `notified → assessing`، مع سجل تحولات للمراجعة القانونية.
**الجهد:** 3–4 س · **Backend + Legal** · **القبول:** محاولة rollback بعد notified تُرفَض وتُسجَّل.

---

## 6. المرحلة P2 — متوسطة وتصلّب (الأسبوع 7–12)

| مُعرّف | الإصلاح | الجهد | المسؤول |
|------|---------|:---:|--------|
| PERF-15/24 | دمج `filter().count()` بـ `values().annotate()`؛ `Count(filter=Q())` واحد | 3–4 س | Backend |
| PERF-16 | caching (Redis) لـ `KPIService.compute` أو حسابه في Celery Beat | 4–5 س | Backend |
| PERF-18/19/22 | فهارس مركّبة: `AnnualSubjectResult(student,school,year)`، `StudentAttendance(student,session__date)`، `student_count` annotate | 3 س | Backend + DB |
| PII-13 | فرض `ConsentRecord` قبل تسجيل بيانات صحية في `ClinicService` | 3–4 س | Backend + Legal |
| SEC-05 | تصلّب CSRF: نمط `X-CSRFToken` من meta + `HTTPONLY=True` | 2 س | Backend |
| REL-02 | نموذج `FileReference(file_path, object_id, model)` + تنظيف الملفات اليتيمة | 4–5 س | Backend |
| P2.1 | استخراج `EncryptionService` مركزي (توحيد fail-safe + logging + rotation) | 5–6 س | Backend + Security |
| P2.2 | لوحة DLQ + مقاييس (زمن المعالجة، العناصر الحرجة) | 4–5 س | DevOps |
| ARCH-03 | رفع تغطية `core`/`notifications`/`behavior`/`assessments` نحو 85% | 20–25 س | QA |
| SEC-06 | فحص محتوى الملفات المرفوعة (magic bytes) لا الامتداد | 3 س | Security |
| SEC-07 | كلمات مرور استيراد عشوائية عبر قناة آمنة | 2 س | Backend |
| PII-08/11 | UUID في أسماء ملفات PDF؛ تسجيل `id` لا البريد | 1 س | Backend |

---

## 7. التحقّق والحوكمة (Definition of Done)

**بعد كل إصلاح، لا يُغلق البند إلا بـ:**
1. **اختبار ارتداد**: `django_assert_num_queries` لبنود الأداء؛ اختبار صلاحية (403/200) لبنود الأمن؛ اختبار تشفير/محو لبنود الخصوصية.
2. **إعادة تشغيل الفاحصات** (محلياً — البيئة الآلية تعطّلت في جلسة التدقيق):
   ```bash
   python .claude/skills/pdppl-pii-audit/scripts/pii_scan.py
   python .claude/skills/nplus1-hunter/scripts/nplus1_scan.py
   python .claude/skills/schoolos-migration-guard/scripts/check_migration.py --pending
   ```
3. **بوابة الجودة**: `ruff check . && mypy . && pytest` تمرّ، والتغطية لا تنزل.
4. **مراجعة أمنية** للبنود 🔴/🟠 قبل الدمج.

**حوكمة مستمرة:** أضِف `pii_scan` و`nplus1_scan` كخطوة في `ci.yml` (تحذيرية أولاً) لمنع ارتداد الخصوصية/الأداء.

---

## 8. الجدول الزمني والموارد (90 يوماً)

| المرحلة | الفترة | النطاق | المخرج |
|---------|--------|--------|--------|
| **1 — إطفاء الحرائق** | أسبوع 1–2 | P0 (8 بنود) | إغلاق كل الحرجة؛ صفر فقد بيانات محتمل |
| **2 — تحصين** | أسبوع 3–6 | P1 (8 بنود) | خصوصية محكمة + أداء الكتابة + حوكمة الجودة |
| **3 — تحسين وصلابة** | أسبوع 7–10 | P2 | caching/فهارس + DLQ dashboard + EncryptionService |
| **4 — رفع التغطية والقبول** | أسبوع 11–13 | ARCH-03 + توثيق | تغطية ≥80% + مراجعة نهائية + جاهزية إنتاج |

**الموارد المقترحة:** 3 Backend + 1 Security + 1 QA + 1 DevOps/SRE + Lead.
**الجهد الإجمالي:** ≈ 240–290 ساعة (P0 ≈ 35 س، P1 ≈ 45 س، P2 ≈ 60 س، التغطية ≈ 25 س، فائض اختبار/مراجعة).
**التكلفة التقديرية:** ≈ 25,000–35,000 دولار أو ما يعادلها داخلياً · **المستهدف النهائي:** 2026-10-06.
**النتيجة المتوقّعة:** الانتقال من **75/100** إلى **90+/100** وإغلاق كل بنود P0.

---

## 9. متتبّع التنفيذ

| البند | الأولوية | الحالة | البدء | النهاية | المسؤول |
|------|:---:|:---:|------|------|--------|
| P0-1 rotate_fernet_key | 🔴 | ⏳ مجدول | 2026-07-08 | 2026-07-12 | Backend+Sec |
| P0-2 national_id في التدقيق | 🔴 | ⏳ | 2026-07-08 | 2026-07-10 | Backend+Sec |
| P0-3 batch الدرجات | 🔴 | ⏳ | 2026-07-08 | 2026-07-15 | Backend |
| P0-4 RLS fail-closed | 🔴 | ⏳ | 2026-07-09 | 2026-07-12 | Backend+DB |
| P0-5 صلابة التشفير | 🔴 | ⏳ | 2026-07-10 | 2026-07-14 | Backend+Sec |
| P0-6 Celery للتوليد | 🔴 | ⏳ | 2026-07-13 | 2026-07-18 | Backend+DevOps |
| P0-7 إكمال المحو | 🔴 | ⏳ | 2026-07-13 | 2026-07-14 | Backend |
| P0-8 DLQ الإشعارات | 🔴 | ⏳ | 2026-07-15 | 2026-07-20 | Backend+DevOps |
| P1 (8 بنود) | 🟠 | ⏳ | 2026-07-21 | 2026-08-10 | فريق مختلط |
| P2 + التغطية | 🟡 | ⏳ | 2026-08-11 | 2026-09-20 | فريق مختلط |

**معايير الإغلاق النهائي:** كل P0 مغلق ومختبَر · صفر تسرّب RLS تحت الحمل · DLQ مستقر < 5/يوم ·
`pii_scan`/`nplus1_scan` نظيفان على المسارات الحرجة · تغطية ≥80% · مراجعة أمنية نهائية + موافقة QA.

---
*خطة موحّدة من التدقيق العدائي (مهارات SchoolOS) + تقرير SWOT، بعد تحقّق مصدري وحسم التناقضات.*
*كل بند قابل للتتبّع عبر مُعرّفه وموقعه (ملف:سطر). الإصلاحات على `D:\shschool_mvp` مباشرة.*
