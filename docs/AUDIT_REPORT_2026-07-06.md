# تقرير التدقيق العدائي الشامل — منصة SchoolOS

**التاريخ:** 2026-07-06 · **الإصدار المُدقَّق:** فرع `main` على `D:\shschool_mvp`
**المنهجية:** تدقيق عدائي متعدّد النطاقات عبر مهارات SchoolOS الخمس + مراجعة مصدرية يدوية سطراً بسطر
**النطاق:** 22 تطبيقاً · 4423 ملف Python · 1306 قالباً · طبقة التشفير والأمن والمعمارية بالكامل
**الوضع:** قراءة فقط — لم تُجرَ أي تعديلات على الكود

---

## 1. الملخّص التنفيذي

المنصة **ناضجة هندسياً بدرجة استثنائية** لمشروع بهذا الحجم: تشفير Fernet/MultiFernet مع fail-closed،
عزل مستأجرين ثلاثي الطبقات (RLS على PostgreSQL + RBAC + فحص كائني)، دورة PDPPL كاملة (موافقة/خرق/محو)،
تدقيق غير قابل للتعديل، بنية Celery ناضجة، و`transaction.atomic` في 90 موضعاً. **التقييم العام: 7.5/10.**

الفجوات ليست في غياب البنية بل في **تنفيذ ناقص نقطي** يخلق مخاطر حقيقية:

| # | أخطر 5 مخاطر | النطاق | الخطورة |
|---|--------------|--------|---------|
| 1 | `rotate_fernet_key` مكسور — تدوير المفتاح يُتلف كل البيانات الصحية والهواتف بصمت | خصوصية | 🔴 حرجة |
| 2 | الرقم الشخصي الخام يُسرَّب إلى AuditLog الدائم وينجو من المحو (تعارض م.18/م.19) | خصوصية | 🔴 حرجة |
| 3 | حفظ/إعادة حساب درجات الفصل: 300–600+ استعلام و90+ قفلاً في طلب POST واحد | أداء | 🔴 حرجة |
| 4 | توليد PDF/Excel والإشعارات الجماعية متزامناً داخل دورة الطلب (لا Celery) | أداء | 🔴 حرجة |
| 5 | تسريب الرقم الشخصي + الهاتف لكل معلم عبر قوائم التسجيل (خرق تقليل البيانات) | خصوصية | 🟠 عالية |

### توزيع النتائج بالخطورة

| النطاق | 🔴 حرجة | 🟠 عالية | 🟡 متوسطة | ⚪ منخفضة | المجموع |
|--------|:---:|:---:|:---:|:---:|:---:|
| الأمن (OWASP/Zero-Trust) | 0 | 1 | 3 | 2 | 6 |
| الخصوصية (PDPPL/PII) | 2 | 5 | 6 | 3 | 16 |
| الأداء (N+1/Celery) | 5 | 9 | 10 | 1 | 25 |
| سلامة البيانات والمعمارية | 0 | 1 | 2 | 2 | 5 |
| **الإجمالي** | **7** | **16** | **21** | **8** | **52** |

---

## 2. المنهجية والأدوات

استُخدمت المهارات المحلية الخمس كإطار للتدقيق، مدعومةً بمراجعة مصدرية يدوية:

- `pdppl-pii-audit` — مسح حقول PII، التشفير، الموافقة، المحو، الخرق، تسريب serializers/السجلّات.
- `nplus1-hunter` — رصد N+1 في Python والقوالب.
- `schoolos-migration-guard` — أمان الترحيلات والأقفال وفقد البيانات.
- `drf-endpoint-scaffold` — مرجع الطبقات لتقييم التزام المعمارية.
- `schoolos-report-ar` — إطار هذا التقرير.

وُزّع العمل على أربعة وكلاء تدقيق متوازين (أمن، خصوصية، أداء، معمارية).

> **قيد منهجي:** بيئة الـ bash عَلِقت على عملية طويلة، فتعذّر تشغيل السكربتات الآلية في هذه الجلسة.
> عُوِّض ذلك بمراجعة مصدرية يدوية مباشرة (أعمق لكن أبطأ). **يُوصى بإعادة تشغيل السكربتات محلياً**
> (`pii_scan.py`, `nplus1_scan.py`, `check_migration.py`) للتحقّق الآلي التكميلي. كل بنود هذا التقرير
> مؤكَّدة من قراءة المصدر الحقيقي (مع تجاهل `.claude/worktrees/*` كنسخ قديمة).

**مفتاح الخطورة:** 🔴 حرجة (فقد بيانات/توقّف/خرق مباشر) · 🟠 عالية (خرق محتمل/تدهور جسيم) ·
🟡 متوسطة (مخاطرة موضعية) · ⚪ منخفضة (تحسين/تصلّب).

---

## 3. الأمن السيبراني (OWASP Top 10 / Zero-Trust)

### الوضع العام: قوي جداً
- `SECRET_KEY` / `ALLOWED_HOSTS` مفروضان في الإنتاج (يرفعان `ImproperlyConfigured` عند الغياب) — `production.py:59,290`.
- `DEBUG=False` افتراضياً؛ CORS **allowlist** لا `ALLOW_ALL`، مع فحص إنتاجي يرفض origins محلية — `production.py:298`.
- ترتيب MIDDLEWARE مثالي: RLS بعد المصادقة وقبل الاستعلامات المحميّة، axes بعد المصادقة، CSP مُطبَّق — `base.py:67-94`.
- SIMPLE_JWT: وصول ساعة، تحديث 7 أيام، `ROTATE_REFRESH_TOKENS=True` — `base.py:351-353`.
- HSTS+preload، كوكيز آمنة، `NOSNIFF`, `X_FRAME_OPTIONS=DENY`, `django-axes` ضد القوة الغاشمة.
- **لا** استخدام لـ `eval/exec/pickle/os.system/mark_safe` في كود المشروع؛ لا SQL خام غير مُعامَل.
- عزل المستأجرين ثلاثي: RLS (`middleware_rls.py`) + RBAC (`api/permissions.py`) + فحص كائني، مع إصلاح IDOR موثّق.

### النتائج

**[SEC-01] RLS يفشل مفتوحاً (fail-open) عند تعذّر ضبط السياق**
🟠 عالية — `core/middleware_rls.py:66-67`
الدليل: `_apply` عند `DatabaseError` يسجّل تحذيراً و**يتابع** الطلب. مع اتصالات مُجمّعة (`CONN_MAX_AGE=600`)،
فشل `set_config` يعني متابعة الطلب بسياق المستأجر الموروث من الطلب السابق على نفس الاتصال.
الأثر: نافذة تسرّب بيانات عبر المدارس (خرق العزل) عند فشل ضبط RLS.
الإصلاح: fail-closed على المسارات المحميّة — ارفع 503/500 إن فشل ضبط RLS بدل المتابعة صامتاً.

**[SEC-02] تدوير refresh token دون قائمة حظر (تحقّق)**
🟡 متوسطة — `shschool/settings/base.py:350-353`
الدليل: `ROTATE_REFRESH_TOKENS=True` موجود، لكن لم أجد `BLACKLIST_AFTER_ROTATION=True` ولا تطبيق
`token_blacklist`. بدونهما، الـ refresh tokens المُدوَّرة/عند الخروج تبقى صالحة حتى انتهائها (7 أيام).
الأثر: لا إبطال حقيقي للجلسة عند الخروج/التدوير — يخالف مبدأ تدوير الأسرار في معايير المشروع.
الإصلاح: فعّل `BLACKLIST_AFTER_ROTATION=True` + أضِف `rest_framework_simplejwt.token_blacklist`.

**[SEC-03] صلاحيات تسمح افتراضياً عند غياب المعرّف (دفاع عميق ناقص)**
🟡 متوسطة — `api/permissions.py:99-100, 138-140`
الدليل: `IsParentOrAdmin` تُرجع `True` عند غياب `student_id` في الـ URL، و`IsSameDepartment` تُرجع
`True` عند غياب `department`. الأمان يعتمد على أن الـ view يفلتر بنفسه.
الأثر: أي view قائمة ينسى الفلترة بالنطاق يكشف بيانات عبر المستخدمين. (بوابة ولي الأمر تفلتر صحيحاً حالياً.)
الإصلاح: deny-by-default حيثما أمكن، أو توثيق إلزامي بأن كل view مرتبط يفلتر بالنطاق + اختبار يثبته.

**[SEC-04] `CSRF_COOKIE_HTTPONLY = False`**
🟡 متوسطة — `shschool/settings/base.py:280` (مطابق لـ PII-12)
مبرّر لطلبات AJAX، لكنه سطح لسرقة توكن CSRF عبر XSS. الإصلaح: نمط `X-CSRFToken` من meta tag + `HTTPONLY=True`.

**[SEC-05] ترحيل يمزج تعديل schema مع تعبئة بيانات**
⚪ منخفضة — `clinic/migrations/0003_...py:58-74`
`AlterField` (تحويل لـ EncryptedTextField) + `RunPython` في ملف واحد. مقبول لجدول العيادة الصغير، لكن
النمط يقفل الجدول أثناء التعبئة (يصطاده `schoolos-migration-guard`). **إيجابية:** التعبئة تمرّ عبر
`encrypt_field` في Python (لا تُخزَّن نصاً صريحاً) وقابلة للعكس وبحارس ضدّ التشفير المزدوج — تنفيذ سليم.

**[SEC-06] أساس كلمة المرور عند الاستيراد = الرقم الشخصي**
⚪ منخفضة — `core/management/commands/import_students_parents.py`
مخفَّف بـ `must_change_password=True`، لكن كلمة مرور مشتقّة من PII معروف قابلة للتخمين قبل أول دخول.
الإصلاح: توليد عشوائي كما في `real_seed`.

---

## 4. الخصوصية وحماية البيانات (PDPPL — قانون قطر 13/2016)

### الوضع العام: جيد جداً مع فجوتين حرجتين (7/10)
بنية ناضجة: fail-closed حقيقي، ثلاثية HMAC للبحث، AuditLog غير قابل للتعديل، دورة موافقة/خرق/محو،
حماية وسائط fail-closed بعزل مدرسي، إخفاء PII على كل معالجات السجلّ (`PIIMaskingFilter`).

### النتائج الحرجة

**[PII-01] `rotate_fernet_key` يترك البيانات الصحية والهواتف غير قابلة للفك**
🔴 حرجة — `core/management/commands/rotate_fernet_key.py:47,77-95`
ثلاثة أعطال: (1) أسماء حقول HealthRecord خاطئة (`_allergies` بشرطة بدل `allergies`) → لا يُعاد تشفير أي سجل صحي؛
(2) `ClinicVisit` (reason/symptoms/treatment) غير مشمول كلياً؛ (3) `phone_encrypted` غير مشمول.
الأثر: بعد تدوير مفتاح وإزالة القديم من `FERNET_OLD_KEYS`، **كل البيانات الصحية والهواتف تصبح غير قابلة
للاسترجاع نهائياً** أو تبقى محميّة بالمفتاح المُخترَق فقط.
الإصلاح: تصحيح أسماء الحقول؛ إضافة `ClinicVisit` و`phone_encrypted`؛ توليد قائمة الحقول ديناميكياً من سجل مركزي.

**[PII-02] الرقم الشخصي الخام في AuditLog الدائم يَنجو من المحو**
🔴 حرجة — `core/signals.py:239` + `core/models/user.py:110-111`
`AuditLog.changes` و`object_repr` (= `str(user)` = `"الاسم (الرقم الشخصي)"`) يخزّنان الرقم الشخصي خاماً في
جدول غير قابل للحذف يُحفَظ صراحةً عبر المحو. `ErasureService` يجهّل الصف الحيّ لكن التاريخ يبقى مسترجَعاً.
الأثر: تعارض غير محلول بين م.18 (المحو) وم.19 (ثبات التدقيق) — المحو ناقص فعلياً.
الإصلاح: سجّل UUID فقط في التدقيق؛ أعِد تعريف `__str__`/`object_repr` بلا رقم شخصي؛ أو استخدم HMAC.

### النتائج العالية
- **[PII-03]** 🟠 `UserBriefSerializer` يكشف `national_id`+`phone` لكل معلم عبر قوائم التسجيل — `api/serializers.py:47-52`. أنشئ serializer قوائم بالاسم فقط.
- **[PII-04]** 🟠 `emergency_contact_name/phone` في HealthRecord نصّ صريح — `clinic/models.py:41-42`. حوّلهما لـ EncryptedTextField.
- **[PII-05]** 🟠 `ClinicVisitSerializer` يعرض البيانات الطبية بلا نسخة «آمنة» — `api/serializers.py:374-390`. افصل الميتاداتا عن المحتوى الطبي.
- **[PII-06]** 🟠 سجلّات سلوك/أمنية لقُصّر نصّ صريح (`violation_description`, `security_notes`, `digital_evidence_notes`) — `behavior/models.py:292+`. شفّر الحقول الحرة.
- **[PII-07]** 🟠 المحو لا يصفّر `national_id_encrypted/hmac` و`phone_encrypted/hmac` — `core/erasure_service.py:164-173`. القيمة الأصلية تبقى قابلة للفك/الربط.

### النتائج المتوسطة والمنخفضة
- **[PII-08]** 🟡 الرقم الشخصي في اسم ملف PDF — `behavior/views.py:851`. استخدم UUID.
- **[PII-09]** 🟡 بيانات السائقين + `gps_link` نصّ صريح — `transport/models.py:26-37`.
- **[PII-10]** 🟡 `EncryptedTextField` fail-open صامت عند فشل الفك — `core/fields.py:20-21`. ميّز «قديم غير مشفّر» عن «فشل حقيقي».
- **[PII-11]** 🟡 تسجيل بريد ولي الأمر عند فشل الإرسال — `behavior/views.py:497`. سجّل id.
- **[PII-12]** 🟡 `CSRF_COOKIE_HTTPONLY=False` (= SEC-04).
- **[PII-13]** 🟡 الموافقة (`ConsentRecord`) موثّقة لا مفروضة تقنياً قبل تسجيل بيانات صحية — أضِف بوابة في `ClinicService`.
- **[PII-14/15/16]** ⚪ النص الخام لـ national_id مبرّر (USERNAME_FIELD) لكنه جذر التسريب؛ سجلّات على قرص مؤقّت؛ كلمة مرور استيراد = الرقم الشخصي.

### إيجابيات مؤكَّدة
تشفير fail-closed حقيقي (`_crypto.py:44-73`)؛ AuditLog immutable (`audit.py:11-24`)؛ حماية وسائط fail-closed
بعزل مدرسي وإجبار تنزيل SVG/HTML ضد XSS المخزّن (`core/views_media.py`)؛ `PIIMaskingFilter` على كل المعالجات؛
إشارات الصحة تسجّل بوليان فقط؛ المحو يحذف الملفات المرفوعة صراحةً.

---

## 5. الأداء (N+1 / الاستعلامات / Celery)

### الوضع العام: طبقة القراءة (API) نظيفة من N+1 عملياً
نمط `querysets.py` موحّد (`with_details()`/`with_student()`) عبر 8 تطبيقات، `select_related/prefetch_related`
و`annotate` بإتقان، خرائط batch في `parents/services.py` و`get_class_results`. **المشكلات مركّزة في الكتابة
الجماعية للدرجات، والعمليات المتزامنة الثقيلة، وقوالب الوحدات الأحدث.**

### النتائج الحرجة
- **[PERF-01]** 🔴 `recalculate_full_class` تسلسلي متداخل — `assessments/services.py:370-379`. 30 طالباً ≈ 300–600+ استعلام و90+ قفلاً. **الحل موجود وغير مستخدم:** `calc_package_scores_batch` (سطر 103) + `bulk_update` + Celery.
- **[PERF-02]** 🔴 `save_all_grades` يُطلق إعادة حساب لكل طالب داخل POST — `assessments/views.py:333-378`. احسب خاماً بـ bulk ثم إعادة حساب واحدة للفصل عبر batch + Celery.
- **[PERF-03]** 🔴 توليد PDF كشوف/شهادات داخل دورة الطلب — `reports/views.py:132-181`. `class_certificates_pdf` يستدعي `get_student_report` (5-6 استعلامات) لكل طالب ثم يصيّر PDF. انقله لـ Celery + جلب batch.
- **[PERF-04]** 🔴 `get_exam_results_reports` — استعلام لكل باقة (N+1) — `reports/services.py:454-467`. 80–150 باقة = 80–150 استعلاماً. اجلب دفعةً بخريطة.
- **[PERF-05]** 🔴 إشعارات جماعية متزامنة من الـ view — `notifications/views.py:63-88`. 100–500 إشعار حاجب. غلّف التنسيق في `@shared_task` (البنية جاهزة).

### النتائج العالية (مختصرة)
- **[PERF-06]** 🟠 تصدير Excel متزامن (مدرسة كاملة) — `reports/views.py:318-357`. → Celery.
- **[PERF-07]** 🟠 `student_profile` سلوك: N+1 على `violation_category`/`reported_by` — طبّق `with_student()` الموجود.
- **[PERF-08]** 🟠 قوالب البدلاء/الجدول: سلاسل FK متعددة — `templates/substitute/*`. أضِف select_related في الـ view.
- **[PERF-09]** 🟠 لوحة النقل: N+1 على `item.bus.*` + `.count` — `transport/querysets.py` فيه `with_details()`/`student_count()` غير مطبَّقة.
- **[PERF-10]** 🟠 قوالب exam_control (المشرفون/الحوادث): N+1 على staff/room/student.
- **[PERF-11]** 🟠 `{{ infractions.count }}` COUNT في القالب — استبدله بـ annotate.
- **[PERF-12]** 🟠 تقرير الأدمن اليومي: N+1 على student/session — `templates/admin/daily_report.html:86`.
- **[PERF-13]** 🟠 `get_quiz_reports` تحميل غير محدود بلا pagination — `reports/services.py:346`.
- **[PERF-14]** 🟠 `class_certificates_pdf` حلقة `get_student_report` — استبدلها بجلب batch.

### النتائج المتوسطة (مختصرة)
`{lvl: qs.filter().count()}` قابلة للدمج (`behavior/services.py:358,415`)؛ `KPIService.compute` ~20 استعلاماً
تسلسلياً بلا caching (`analytics/services.py:252`)؛ `.count()/.first()` في حلقات (`quality/views_executor.py`)؛
فهارس مركّبة يُنصح بها على `AnnualSubjectResult(student,school,year)` و`StudentAttendance`؛
`ClassGroupSerializer.get_student_count` COUNT لكل فصل — استخدم annotate.

### إيجابيات مؤكَّدة
طبقة `api/views.py` نظيفة من N+1؛ `get_class_results`/`get_attendance_report` نمط batch مثالي؛
`parents/services.py` batch كامل؛ `analytics` يستخدم `annotate(filter=Q())`؛ بنية Celery ناضجة
(`notifications/tasks.py` مع retry/backoff، `behavior/tasks.py` بـ `.iterator()`).

---

## 6. سلامة البيانات والمعمارية

### الوضع العام: التزام قوي بـ Clean Architecture
- **Fat Services / Skinny Models:** كل تطبيق له `services.py`؛ `transaction.atomic` في **90 موضعاً** عبر 40 ملفاً (طبقة كتابة ذرّية).
- **نماذج أساس موحّدة:** `TimeStampedModel` (UUID PK)، `AuditedModel`، `SoftDeleteModel`، `SchoolScopedModel` — `core/models/base.py`.
- **DRF مطبّق نظيفاً:** serializers للعرض، selectors/services للمنطق، views نحيفة.

### النتائج
**[ARCH-01] تغطية اختبارات دون الهدف**
🟡 متوسطة — `pyproject.toml:100`
التغطية الفعلية ≈63% مقابل هدف 85% (`--cov-fail-under=60`). المسارات الحرجة (حساب الدرجات، المحو، RLS،
التشفير) تحتاج تغطية أعلى خاصةً بعد إصلاح البنود الحرجة. الإصلاح: ارفع الأرضية تدريجياً واكتب اختبارات
`django_assert_num_queries` على مسارات القوائم (تثبّت غياب N+1 وتمنع ارتداده).

**[ARCH-02] الكتابة الجماعية للدرجات ليست idempotent-batch**
🟠 عالية — `assessments/services.py` (متقاطع مع PERF-01/02)
مسار الكتابة يعيد الحساب لكل طالب بدل batch، ما يجعله بطيئاً وعرضةً لتعارض الأقفال. الإصلاح المعماري:
افصل «حفظ الدرجات الخام» (bulk) عن «إعادة الحساب» (batch واحد للفصل)، واجعل الأخير مهمة idempotent.

**[ARCH-03] ترحيل schema+data ممزوج**
⚪ منخفضة — `clinic/migrations/0003` (= SEC-05). افصل مستقبلاً لتقليل زمن القفل.

**[ARCH-04] fail-open في التشفير يخفي مشاكل السلامة**
⚪ منخفضة — `core/fields.py` (= PII-10). يجعل تشخيص فشل التشفير أصعب.

---

## 7. خارطة الإصلاح ذات الأولوية

### P0 — فوري (قبل أي تدوير مفاتيح أو نشر كبير)
1. **إصلاح `rotate_fernet_key`** (PII-01) — أخطر فجوة توافر: تدوير اليوم يُتلف البيانات الصحية بصمت.
2. **إزالة الرقم الشخصي الخام من AuditLog** (PII-02) + **إكمال المحو** (PII-07) — يحلّان تعارض م.18/م.19.
3. **fail-closed على RLS** (SEC-01) — إغلاق نافذة تسرّب المستأجرين.

### P1 — عاجل (هذا السبرنت)
4. **إعادة صياغة كتابة/حساب الدرجات** (PERF-01/02, ARCH-02) عبر `calc_package_scores_batch` + `bulk_update` + Celery.
5. **نقل PDF/Excel/الإشعارات الجماعية إلى Celery** (PERF-03/05/06).
6. **إخفاء national_id/phone عن قوائم المعلمين** (PII-03) + تشفير الحقول الحسّاسة المتبقية (PII-04/05/06/09).
7. **قائمة حظر refresh tokens** (SEC-02).

### P2 — مهم (السبرنت التالي)
8. إزالة N+1 من التقارير والقوالب (PERF-04, 07–14) عبر `with_details()`/select_related الموجودة.
9. caching لـ KPIs + فهارس مركّبة (PERF المتوسطة).
10. فرض الموافقة تقنياً (PII-13)، رفع تغطية الاختبارات نحو 85% (ARCH-01)، تصلّب CSRF (SEC-04).

---

## 8. الخلاصة

القاعدة الأمنية والمعمارية للمنصة **قوية ولا تحتاج إعادة تصميم**. الإصلاحات كلها **نقطية ومحدّدة الموقع**.
الأولوية القصوى لثلاثة بنود حرجة (تدوير المفاتيح، الرقم الشخصي في التدقيق، fail-open في RLS) لأنها تمسّ
بيانات قُصّر وبيانات صحية تحت PDPPL. بعد معالجة P0/P1، تنتقل المنصة من «ناضجة مع فجوات حرجة» إلى
«جاهزة للإنتاج الحكومي بثقة عالية».

> **الخطوة التالية الموصى بها:** إعادة تشغيل السكربتات الثلاثة محلياً للتحقّق الآلي، ثم فتح تذاكر P0
> فوراً. أستطيع توليد رقعات (patches) للبنود الحرجة عند الطلب.

---
*أُعدّ هذا التقرير عبر مهارات SchoolOS الخمس + مراجعة عدائية يدوية. النتائج مؤكَّدة من المصدر الحقيقي على*
*`D:\shschool_mvp` (بلا تعديل). البنود التي تحمل مواقع ملف:سطر قابلة للتحقّق المباشر.*
