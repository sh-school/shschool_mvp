# الفاحص `pii_scan.py` — كيف يعمل وكيف تقرأ مخرجَه

متى تقرأ هذا الملف: حين تشغّل الفاحص وتقرأ نتائجه، أو حين تفكّر في تعديله، أو حين يخرج «لا شيء» وتشكّ.

## التشغيل
```bash
python .claude/skills/pdppl-pii-audit/scripts/pii_scan.py                 # كلُّ المستودع عدا الاختبارات
python .claude/skills/pdppl-pii-audit/scripts/pii_scan.py --app clinic     # تطبيقٌ واحد
python .claude/skills/pdppl-pii-audit/scripts/pii_scan.py --models-only | --serializers-only | --logs-only
python .claude/skills/pdppl-pii-audit/scripts/pii_scan.py --include-tests  # يضمّ tests/ وtest_*
python .claude/skills/pdppl-pii-audit/scripts/pii_scan.py --root <مسار>    # جذرٌ صريح
```
- الجذر: أقربُ سلفٍ لمجلّد التشغيل فيه `manage.py` — شغّله من شجرة عملك.
- رمزُ الخروج: 0 لا بندَ حرجاً، 1 بندٌ حرج، **2 لم يُفحص ملفّ** (جذرٌ أو `--app` خاطئ).
- لا يحتاج Django ولا قاعدة: قراءةٌ نصّيّةٌ فقط، يعمل على المضيف مباشرةً.

## ما يلتقطه
| الفحص | القاعدة | الخطورة |
|---|---|---|
| النماذج | حقلٌ `CharField`/`TextField`/`EmailField`/`GenericIPAddressField` اسمُه يحمل مقطعاً شخصيّاً ولا `<name>_encrypted` بجانبه | صحّيٌّ/نفسيّ/دينيّ: حرج؛ تعريفيّ: عالٍ؛ بريدٌ/صورة وIP: معلومة |
| المُسلسِلات | `fields = [...]` أو `(...)` فيها مقطعٌ شخصيّ، أو `fields = "__all__"` | عالٍ |
| السجلّات | `<شيءٌ>log<شيءٌ>.info/…(` أو `print(` ونصُّ النداء (حتى ستّة أسطر) فيه `.phone` أو `phone=` أو `['phone']`… | حرج |

يتخطّى: `migrations`، `.venv`، `node_modules`، `staticfiles`، `_archive`، `.claude` — **نسبةً إلى الجذر**. والأسماءُ المنتهية بـ`_subject`/`_template`/`_label`/`_help_text`/`_format`/`_count`.

## نتائجُ `main` المعروفة (2026-09-28، 630 ملفّاً: حرج 3 · عالٍ 5 · معلومة 5)
| البند | الحكم |
|---|---|
| `clinic/models.py` — `blood_type` `CharField` | **حقيقيّ**: بيانٌ صحّيٌّ صريح؛ قرارُ الـDPO (تشفيرٌ أو تبريرٌ مكتوب) |
| `student_affairs/services.py` — `logger.info(... full_name ..., national_id)` | **حقيقيّ**: الاسمُ لا يُقنَّع، والرقمُ لا يُقنَّع في التطوير |
| `scripts/real_seed.py` — `print(... u.national_id)` | حقيقيٌّ منخفضُ الأثر (سكربتُ زرعٍ محلّيّ) — يُصلح حين يُلمس |
| `core/models/school.py` — `phone`، `address`، `email` | **إيجابيٌّ كاذب**: بياناتُ اتّصالٍ مؤسّسيّة للمدرسة لا لشخص |
| `api/serializers.py:44` `SchoolSerializer` — `phone` | إيجابيٌّ كاذب للسبب نفسه |
| `api/serializers.py:56` `UserBriefSerializer` | مقبول: يحذف ويستر في `to_representation` |
| `api/serializers.py:100` `MeSerializer` | مقبول: المستخدمُ يرى بياناتِه هو (م.6) |
| `ip_address` في `AuditLog` و`PermissionAuditLog` و`developer_feedback/models.py` | معلومة: IP بيانٌ شخصيّ يحكمه الاحتفاظ لا التشفير |
| `core/models/user.py` — `email` | معلومة: البريدُ الشخصيّ صريحٌ اليوم؛ لا قرارَ مسجَّلاً بتشفيره |

## حدودُه (اعرفها قبل أن تقول «سليم»)
- استدلالٌ بالأسماء: حقلٌ اسمُه `notes` يحمل تشخيصاً لا يُرى؛ و`JSONField` لا يُفحص.
- لا يقرأ القوالب — ستر الرقم في القوالب يحرسه `tests/test_national_id_never_bulk.py`، والصورُ حرّاسُها في `10-platform-controls.md`.
- لا يعرف الإذن: مُسلسِلٌ «عالٍ» قد يكون محميّاً بـview صحيحة؛ اقرأ الـview.
- التسجيلُ عبر متغيّرٍ وسيط (`nid = user.national_id` ثمّ `logger.info("%s", nid)`) لا يُلتقط.
- لا يعرف `print` في سكربتٍ لا يعمل في الإنتاج من غيره — الحكمُ للسياق.

## لماذا تغيّر عن الإصدار السابق (دليلٌ مقيس)
- الإصدارُ السابق كان يتخطّى أيَّ ملفٍّ في مساره المطلق `.claude` أو `worktrees` — فكلُّ شجرة عملٍ (`D:\shschool_mvp\.claude\worktrees\<اسم>`) تُفحص صفراً وتُعلن «سليم» برمز 0. ثبت بتشغيله في شجرة عملٍ حقيقيّة: «0 · 0 · 0».
- كان يطبع رموزاً تعبيريّة تُسقط طرفيّةَ ويندوز بلا `PYTHONIOENCODING=utf-8`.
- كان يعدّ `messages.warning(` تسجيلاً، و`blueprint(` طباعة، ولا يرى القيمةَ في سطرٍ تالٍ من النداء نفسه.
- كان يفحص `tests/` افتراضاً فيُحرِّج نصوصاً داخل `assert`.
- لم يكن يرى `fields = "__all__"` ولا صيغةَ الصفّ `(...)`.

## أنماطٌ مضادّة
- قراءةُ «لا شيء» حكماً بالسلامة دون النظر في «ملفّاتٌ مفحوصة: N».
- إضافةُ مسارٍ إلى التخطّي لإسكات بندٍ حقيقيّ.
- ترقيةُ الفاحص إلى حارسٍ في CI دون قرار — هو أداةُ مراجعةٍ استدلاليّة، وحرّاسُ المنصّة هي البوّابة.
