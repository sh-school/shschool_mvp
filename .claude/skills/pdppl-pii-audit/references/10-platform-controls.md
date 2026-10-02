# أدواتُ الخصوصيّة القائمة وحرّاسُها — لكلّ مسارٍ من الثمانية

متى تقرأ هذا الملف: حين تحتاج أن تعرف «بماذا تعالج المنصّةُ هذا أصلاً؟» قبل أن تكتب شيئاً، أو أيَّ اختبارٍ تشغّل لتثبت أنّك لم تكسر حمايةً قائمة.

كلُّ ما هنا موجودٌ على `main` (تحقّقٌ 2026-09-28). استعمله ولا تكتب بديلاً.

## 1. التخزين (التشفير)
| الأداة | الموضع | ملاحظة |
|---|---|---|
| `EncryptedTextField` | `core/fields.py` | يشفّر عند الحفظ ويفكّ عند القراءة؛ **لا يصلح للبحث** (غيرُ حتميّ)؛ يرفض الحفظ إن فشل التشفيرُ ومعه مفتاح (fail-closed) |
| `encrypt_field` / `decrypt_field` / `hmac_field` | `core/models/crypto.py` | MultiFernet: `FERNET_KEY` للتشفير و`FERNET_OLD_KEYS` للفكّ؛ غيابُ المفتاح في الإنتاج `ImproperlyConfigured` |
| الثلاثيّة | `core/models/user.py` (`national_id`، `phone`) | خامٌ (اسمُ الدخول يشترطه Django) + `_encrypted` + `_hmac` تُملأ في `save()` — وحفظُ `update_fields=["phone"]` يضمّ أختيه تلقائياً |
| أوامرُ إدارة | `populate_phone_encryption`، `repair_pii_columns` (core)، `classify_health_record_encryption` (clinic)، `rotate_fernet_key` (governance) | التعبئةُ والإصلاحُ عبر ORM لا SQL خام |

## 2. العرض الجماعيّ (القوائم والبحث وJSON)
- `core/privacy.py::mask_national_id` و`{% load privacy %}{{ x|mask_id }}` — آخرُ أربع خاناتٍ ظاهرة.
- القاعدة المكتوبة (2026-09-14) في رأس `core/privacy.py`: جماعيٌّ ← مستورٌ دائماً؛ فرديٌّ رسميٌّ لصاحبه ← كاملٌ مع تدقيق؛ الاستثناءُ بالاسم.
- `api/serializers.py::UserBriefSerializer` يحذف الرقمَ والهاتف لغير الإدارة/القيادة ويستر الرقمَ حتى للقيادة؛ `UserSafeSerializer` بالاسم وحده.
- الحارس: `tests/test_national_id_never_bulk.py` (القوالب، ردود JSON، المصدِّرون، Excel).

## 3. التصدير (PDF/Excel)
- `core.audit_export.log_export(request, kind, rows=…, full_national_id=…)` — سطرُ `AuditLog(action="export")` بلا اسمٍ ولا رقم.
- التصديرُ الخلفيّ `core/exports/` (ADR-0007): البنّاءُ يعلن `rows` و`full_national_id` في `ExportResult` فيكتب العاملُ سطرَ `<kind>:built`؛ ملفّاتُ المهامّ تُحذف بعد 24 ساعة.
- Excel: الرقمُ كاملٌ حيث يعود الملفُّ بالرفع الوزاريّ (قائمةُ `EXCEL_FULL_NUMBER` في الحارس) ومستورٌ في غيره؛ وحقنُ الصيغ يُحيَّد بـ`core/excel_safety.py::neutralize_formula_value`.
- التفاصيلُ الشكليّة للتقرير في مهارة `schoolos-report-ar`.

## 4. السجلّات وSentry
- `core/logging_filters.py::PIIMaskingFilter` مركَّبٌ في `LOGGING` الإنتاج (`shschool/settings/production.py`) — يقنّع الرقمَ والهاتفَ والبريد بالأنماط.
- `core/sentry_config.py::before_send` + `send_default_pii=False` (الإنتاج والتجريب).
- ما لا نمطَ له (الاسم، عنوانُ الإشعار ونصُّه) لا يحميه القناع: يُمنع من المصدر. الحارسان: `tests/test_log_data_minimization.py` (حزمة `notifications`) و`tests/test_sentry_privacy.py`.

## 5. الملفّات المرفوعة
- `core/photo_privacy.py::clean_photo` — يحوّل (HEIC أيضاً) ويصغّر ويمحو EXIF/GPS، والحكمُ بالبايتات لا بالامتداد.
- الحرّاس: `test_uploads_are_photo_cleaned`، `test_tardiness_excuse_photo_privacy`، `test_staff_exception_evidence_privacy`، `test_quality_evidence_privacy`.

## 6. الموافقة
- `ConsentRecord` (`core/models/audit.py`): وليُّ أمر × طالب × نوعُ بيان، فريدٌ ثلاثيّاً؛ `withdraw()` **لا يحفظ** — احفظ بعده.
- بوّابةُ موافقة وليّ الأمر: `core/parent_consent.py` (`needs_parent_consent`، `consent_blocks`) — قرارُ المالك 2026-09-16: الكادرُ الذي هو وليُّ أمرٍ لا يُحجب عن عمله. الحارس: `tests/test_parent_consent_gate.py`.
- `purge_parent_consents` (أمرُ إدارة) وحارسُه `tests/test_purge_parent_consents.py`.

## 7. المحو
- `ErasureRequest` + `api/views_erasure.py` (يطلبه وليُّ الأمر أو الإدارة؛ القائمةُ والموافقةُ والرفض لـ`IsSchoolAdmin`) + `governance/erasure_service.py::ErasureService.execute`.
- الخدمة تجهّل الطالبَ عبر قائمتين صريحتين: `_lazy_student_fk_models` و`_lazy_file_field_models`، وتُبقي `AuditLog` بفصل الهويّة.
- الحارسان: `tests/test_erasure.py`، `tests/test_erasure_files.py`. **لا حارسَ يكتشف نموذجاً جديداً نُسي من القائمتين.**

## 8. الاحتفاظ
- `governance/retention.py` + المهمّة `core.enforce_data_retention` (أسبوعيّاً) + `python manage.py enforce_retention [--apply]`.
- `PDPPL_DATA_RETENTION_DAYS` (الافتراض 730، و0 يعطّل) — السياسةُ كاملةً في `docs/privacy/data_retention.md`: ما يُحذف بعد المدّة وما يُحفظ ولماذا.
- الحارسان: `tests/test_data_retention.py`، `tests/test_retention_setting_never_breaks_boot.py`.

## وحرّاسٌ عامّة
- `scripts/check_personal_data.py` (وظيفةُ `secrets-scan`) و`tests/test_personal_data_guard.py`: لا رقمَ شخصيّاً ولا جوّالاً بهيئة الحقيقيّ في ملفٍّ متتبَّع.
- `core/private_data.py`: أسماءُ الموظّفين وقواعدُ ربطها من JSON خارج المستودع العامّ (REP-07b).
- `tests/test_auditlog_immutability.py`، `tests/test_clinic_encryption.py`، `tests/test_health_record_encryption_audit.py`، `tests/test_pii_masking.py`، `tests/test_national_id_masking.py`.
- خريطةُ الحرّاس كلُّها: `docs/governance/regression_guards.md` (ومهارة `schoolos-quality-guards` لقراءة فشلها).

## أنماطٌ مضادّة
- كتابةُ دالّة ستر أو مرشِّح تسجيلٍ أو منظّف صورٍ جديد بجانب القائم.
- الاعتمادُ على `PIIMaskingFilter` لحماية الأسماء أو على بيئة التطوير (لا مرشّحَ فيها).
- استدعاءُ `ConsentRecord.withdraw()` دون `save()`.
- إضافةُ نموذجٍ يحمل الطالبَ دون سطرٍ في `governance/erasure_service.py`.
- تعطيلُ حارسٍ أو إضافةُ اسمٍ إلى قائمة استثنائه دون قرارٍ مسجَّلٍ في المراجعة.
