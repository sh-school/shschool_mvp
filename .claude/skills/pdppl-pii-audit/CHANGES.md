# CHANGES — pdppl-pii-audit

الأصل: `snapshot/.claude/skills/pdppl-pii-audit/` (SKILL 105 سطراً، مرجعٌ واحد 87، سكربت 170). التحقّقُ على `origin/main@81bc4937` (2026-09-28) وعلى نصّ القانون في بوّابة الميزان.

## سجلُّ الادّعاءات
| # | الادّعاء في الأصل | الحكم | الدليل |
|---|---|---|---|
| 1 | `core.fields.EncryptedTextField` يشفّر/يفكّ تلقائيّاً | صحيح | `core/fields.py` |
| 2 | `encrypt_field`/`decrypt_field`/`hmac_field` في `core/models/crypto.py`، MultiFernet | صحيح | `core/models/crypto.py` |
| 3 | `FERNET_KEY`+`FERNET_OLD_KEYS`+`rotate_fernet_key`، fail-closed | صحيح | `governance/management/commands/rotate_fernet_key.py`؛ `_get_fernet` |
| 4 | `AuditLog` manager يمنع UPDATE/DELETE | صحيحٌ ناقص | يُستثنى `update(user=None)` لفصل الهويّة — `_ImmutableQuerySet` |
| 5 | `ConsentRecord`، `ErasureRequest` + `api/views_erasure.py`، `BreachReport` + `breach/` | صحيح | `core/models/audit.py`؛ `ls breach/` |
| 6 | الثلاثيّة في `core/models/user.py` لـ`national_id`/`phone` | صحيح | `core/models/user.py:30-55,127-137,164-187` |
| 7 | `populate_phone_encryption` | صحيح | `core/management/commands/` |
| 8 | `UserBriefSerializer` يعرض national_id/phone — «تأكّد من الإذن» | قديم | يحذفهما لغير الإدارة ويستر الرقمَ للقيادة (`to_representation`) |
| 9 | `UserSafeSerializer` (الاسم فقط)، `IsTeacherOrAdmin` | صحيح | `api/serializers.py:84`؛ `api/permissions.py:56` |
| 10 | `AXES_SENSITIVE_PARAMETERS` يخفي كلمة المرور | صحيح | `shschool/settings/base.py:518` |
| 11 | `ROTATE_REFRESH_TOKENS=True` | صحيح (هامشيّ) | `base.py:406`؛ وبابُ JWT مطفأٌ (`API_JWT_ENABLED`) — `regression_guards.md` |
| 12 | `clinic.HealthRecord` مشفّرٌ بـ`EncryptedTextField` ومنه فصيلةُ الدم | خاطئٌ جزئيّاً | الثلاثةُ الطبّيّة وجهةُ الطوارئ مشفّرة؛ `blood_type` `CharField` صريح (`clinic/models.py:40`) |
| 13 | «تشفير يدويّ get/set — نمط clinic.HealthRecord» (السكربت) | قديم | وُحّدت على الحقل الشفّاف (`[PII-11]` في `clinic/models.py`) |
| 14 | م.2 = الموافقة | خاطئ | م.4 (م.2 نطاقُ التطبيق) — الميزان |
| 15 | م.4 = حقُّ المحو | خاطئ | م.5 — الميزان |
| 16 | م.14 = إخطار الخرق؛ م.16 = الخاصّة | صحيح | الميزان |
| 17 | «NDPO» الجهة المختصّة | قديم | الإشرافُ لدى الوكالة الوطنيّة للأمن السيبرانيّ (الشؤون الوطنيّة للحوكمة والضمان)؛ رابطُ صفحة القانون القديم يُحوَّل إلى ncsa.gov.qa |
| 18 | «المسار الوحيد: D:\shschool_mvp مباشرة» | قديم (أُلغي 2026-09-08) | `CLAUDE.md` القاعدة رقم 1 |
| 19 | «الوصولُ الصحّيّ للممرضة/القيادة» | لا يمكن التحقّق كاملاً | الدورُ `nurse` قائم (`core/models/access.py`)؛ لم تُراجَع صلاحيّاتُ كلّ view عيادة |
| 20 | «SIMPLE_JWT + كوكيز آمنة فقط» | صحيحٌ للجلسة | `SESSION_COOKIE_HTTPONLY/SAMESITE` (base) و`SECURE` (production) |
| 21 | وصفُ السكربت: «فحص شامل» من أيّ موضع | **خاطئ في كلّ شجرة عمل** | تشغيلُه في `D:/shschool_mvp/.claude/worktrees/blissful-neumann-18e46b` أعطى 0·0·0 برمز 0؛ والنسخةُ الجديدة 3·5·5 برمز 1 |

## التغييرات
| البند | القديم | الجديد | السبب | الدليل |
|---|---|---|---|---|
| الوصف | عربيٌّ فقط، كلمة «moافقة» مكسورة، بلا «ليست لـ» | إنجليزيٌّ ثمّ عربيٌّ pushy ثمّ «ليست لـ» بأربع مهاراتٍ بديلة | الكرّاسة §2 | BRIEF.md |
| سطر المسار | «D:\shschool_mvp مباشرة» | «العمل في شجرة عملك» + إحالةٌ إلى `schoolos-flow`/`schoolos-git-safety` | قاعدةٌ ملغاة | CLAUDE.md |
| أرقامُ المواد | م.2/م.4/م.14/م.16 وتعيينٌ عامّ | مرجعُ `00-pdppl-articles.md` بجدولٍ من النصّ + جدولُ تعليقات الشيفرة المخالفة | اقتباسٌ خاطئ في تقرير امتثال | الميزان LawID=7121 |
| الـ72 ساعة | «خلال المدّة النظاميّة» | النصُّ لا يحدّد، والإرشادُ `PDPPL-02050217E` يحدّد 72 ساعة | تمييزُ القانون عن الإرشاد | ncsa.gov.qa؛ `BreachReport.save` |
| الأدوات القائمة | 8 صفوف | 8 مساراتٍ بأدواتها وحرّاسها (ستر، تدقيق التصدير، قناع السجلّ، Sentry، الصور، بوّابة الموافقة، قائمتا المحو، الاحتفاظ) | لا اختراعَ لما هو قائم | `core/privacy.py`، `core/audit_export.py`، `core/logging_filters.py`، `core/sentry_config.py`، `core/photo_privacy.py`، `core/parent_consent.py`، `governance/erasure_service.py`، `governance/retention.py` |
| قاعدةُ المحو | «وثّق نطاق المحو» | «نموذجٌ يحمل الطالب يُضاف إلى `_lazy_student_fk_models`/`_lazy_file_field_models`؛ ولا حارسَ يكتشف المنسيّ» | فجوةٌ حقيقيّة | `governance/erasure_service.py:31,74` |
| `ConsentRecord.withdraw()` | — | «لا يحفظ — احفظ بعده» | فخٌّ في الشيفرة | `core/models/audit.py:211` |
| الـDPO | «دور القيادة» | المالكُ نفسُه هو الـDPO؛ قراراتُ م.16 والإخطار عنده | ذاكرة | `user_dpo_role.md` |
| الفخاخ | 6 أخطاءٍ عامّة | 8 فخاخ خطأ:/الصواب: منها موجودٌ اليوم (`student_affairs/services.py`، `blood_type`) | الكرّاسة §2 | نتيجةُ الفاحص على main |
| السكربت: التخطّي | يقارن أجزاءَ المسار **المطلق** بـ`.claude`/`worktrees` | يقارن الأجزاءَ **النسبيّة** للجذر | صفرُ ملفّاتٍ في كلّ شجرة عمل | تشغيلٌ قبل/بعد (البند 21) |
| السكربت: الجذر | `parents[4]` ثابت | `--root` أو أقربُ سلفٍ فيه `manage.py`، ورمز 2 إن لم يُفحص ملفّ | لا «سليم» على ما لم يُقرأ | اختبارُ `--app nosuch` ← 2 |
| السكربت: الترميز | رموزٌ تعبيريّة، يسقط على cp1252 | وسومٌ نصّيّة و`stdout.reconfigure(utf-8)` | ويندوز؛ الكرّاسة: لا إيموجي | — |
| السكربت: السجلّات | `.warning(` أيَّ كائن، و`print` داخل `blueprint(`، سطرٌ واحد | مسجِّلٌ `*log*.<level>(` أو `print` كلمةً، ونصُّ النداء حتى 6 أسطر | إيجابيٌّ كاذب وسلبيٌّ كاذب | التقط `student_affairs/services.py:585` الذي فاته القديم |
| السكربت: المُسلسِلات | `[...]` فقط | و`(...)` و`"__all__"` | أخطرُ صيغةٍ كانت غير مرئيّة | مثبَّتٌ في اختبار عيّنات |
| السكربت: الأسماء | «email» في `fail_email_subject` = بيانٌ شخصيّ؛ `ip_address` = «عنوان» عالٍ | لواحقُ مستثناة؛ IP معلومةٌ يحكمها الاحتفاظ | ضجيج | `notifications/models.py:233,238` اختفيا |
| السكربت: الاختبارات | يفحص `tests/` افتراضاً | `--include-tests` اختياريّ | نصوصُ `assert` حُرِّجت | `tests/test_security_codeql_hotfix.py:107` |
| البنية | SKILL + مرجع | SKILL (≤120) + `00` المواد + `10` الأدوات + `20` الأنماط + `30` الفاحص + `99` الاختبارات | الكرّاسة §2 | — |

الاختبار: الفاحصُ على main (630 ملفّاً): حرج 3 · عالٍ 5 · معلومة 5، رمز 1؛ في شجرة عملٍ حقيقيّة النتيجةُ نفسُها (القديم: 0 · 0 · 0)؛ عيّناتٌ مختلَقة تحت مسارٍ فيه `.claude/worktrees/` التقطت الحالاتِ الثماني وتخطّت الثلاثيّةَ والمشفَّرَ ولاحقةَ `_subject` و`migrations` و`tests/` و`blueprint(`؛ `ruff check` نظيف. لا ملفّاتٌ مؤقّتة في التسليم.

## يحتاج قرارَ المالك أو تأكيدَه
1. **`HealthRecord.blood_type` صريح** — تشفيرٌ (هجرةٌ بنوع `TextField`) أم تبريرٌ مكتوبٌ بأنّه يُعرض للإسعاف؟ (قرارُ DPO)
2. **سطرُ `student_affairs/services.py:585`** يسجّل الاسمَ والرقمَ عند إنشاء طالب — إصلاحٌ صغيرٌ يُسند لمسارٍ ما.
3. **تعليقاتُ أرقام المواد في الشيفرة متضاربةٌ مع النصّ** (الجدول في `00-pdppl-articles.md`) — تُصحَّح بطلبٍ واحدٍ أم تُترك؟
4. **لا حارسَ يكتشف نموذجاً يحمل الطالبَ ونُسي من `ErasureService`** — هل يُبنى (مقارنةٌ آليّة لكلّ FK إلى `CustomUser` باسم `student`)؟
5. **م.6 (حقُّ الاطّلاع ونسخة البيانات)** لا أداةَ مخصّصةً له — فجوةٌ أم خارجُ النطاق؟
6. **تصريحُ م.16** لمعالجة بيانات الأطفال والصحّة من الإدارة المختصّة — هل حُصل عليه؟ لا أثرَ له في المستودع ولا في الذاكرة (غيرُ موثَّق).
7. **البريدُ الشخصيّ `CustomUser.email` صريح** — مقبولٌ أم يُشفَّر؟
