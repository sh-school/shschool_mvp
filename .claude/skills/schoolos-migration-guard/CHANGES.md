# CHANGES — schoolos-migration-guard

الأصل: `snapshot/.claude/skills/schoolos-migration-guard/` (SKILL 108 سطراً بلا مراجع، سكربت 260). التحقّقُ على `origin/main@81bc4937` (2026-09-28)، وفي مختبرٍ معزولٍ خارج المستودع: Django 5.2.17 وdjango-migration-linter 6.0.0 من صورة `shschool_mvp-web`، وPostgreSQL 18 في حاويةٍ مؤقّتة أُطفئت بعده.

## سجلُّ الادّعاءات
| # | الادّعاء في الأصل | الحكم | الدليل |
|---|---|---|---|
| 1 | Django 5.2 | صحيح | `requirements.txt`: Django==5.2.17 |
| 2 | PostgreSQL 16 | قديمٌ للإنتاج | الإنتاج 18 (`.github/workflows/backup.yml`)، المحلّيّ 18 (`docker-compose.yml`)، CI 16؛ و`README.md`/`DEPLOYMENT-RAILWAY.md` قديمان |
| 3 | «المسار الوحيد `D:\shschool_mvp`، لا worktrees» | قديمٌ مخالف | `CLAUDE.md` القاعدة رقم 1 (2026-09-08) |
| 4 | الفاحص يشغّل `makemigrations --check --dry-run` | صحيحٌ في الحاوية؛ خاطئٌ خارجها | على المضيف يطبع «توجد تغييرات models» فوق Traceback (رمزُ الخطأ يُقرأ تغييراً) — مُعاد إنتاجه |
| 5 | `--sql` يكشف الأقفال بالبحث عن «ACCESS EXCLUSIVE/REWRITE» في `sqlmigrate` | خاطئ | `sqlmigrate` لا يطبع أنماطَ الأقفال أبداً (مخرجاتُ المختبر)، فالفحصُ أخضرُ دائماً؛ ويعمل مع `--app` وحدها |
| 6 | `AddField` NOT NULL بلا default ⇒ إعادةُ كتابة + قفل | جزئيّ | على جدولٍ فيه صفوف يسقط أصلاً؛ والبديلُ الثلاثيّ صحيح، والأبسط `db_default` |
| 7 | `AddField` بـdefault ثابت «آمنٌ على PG16» (🟠) | خاطئٌ في المشروع | Django يُلحق `DROP DEFAULT` والمدقّقُ يُسقطه NOT_NULL (مختبر)؛ العرفُ `db_default` (`operations/migrations/0053_excuse_review.py`) |
| 8 | Remove/Delete/Rename 🔴 على مرحلتين | صحيح | `CLAUDE.md`، `tests/test_migration_linter_wiring.py` |
| 9 | كلُّ `AlterField` يُعلَّم، و🔴 إن احتوى اسمُ النموذج «session/grade/audit…» | ضجيج | `verbose_name` وحده `(no-op)` (مختبر)؛ المطابقةُ الجزئيّة تصيب `examsession` وأمثاله |
| 10 | `RunPython` بلا `reverse_code` 🔴 | القاعدةُ صحيحة، الكشفُ خاطئ | يتجاهل الوسيطَ الموضعيّ `RunPython(f, b)` — 68 إنذاراً كاذباً على هجرات main |
| 11 | خلطُ المخطّط والبيانات 🔴 | مبالغ | وثائق Django تحذّر (pending trigger events)؛ على main سوابقُ مختلطةٌ مرّت (`behavior/migrations/0013_…`) ⇒ 🟠 |
| 12 | `AddIndexConcurrently` + `atomic = False` | صحيح؛ الكشفُ نصّيّ | تعليقٌ فيه «atomic = False» يخدعه (حالة c08)؛ السابقة `operations/migrations/0055_…` |
| 13 | القيودُ (UNIQUE/CHECK/FK) تُنشأ `NOT VALID` ثمّ `VALIDATE` | خاطئٌ لـUNIQUE | PostgreSQL يقبل `NOT VALID` لـCHECK وFK فقط؛ والمدقّقُ يُسقط ADD_UNIQUE (مختبر) |
| 14 | «الآمن»: `AddField(null=True)`، `verbose_name`، `AlterModelOptions`… | صحيح | مختبر (`no-op`) |
| 15 | `core.fields.EncryptedTextField`، `encrypt_field` في `core/models/crypto.py` | صحيح | `core/fields.py`، `core/models/crypto.py` (أُعيدت تسميته من `_crypto.py` في #684) |
| 16 | «ممنوع raw SQL على الحقول المشفّرة» | خاطئٌ مطلقاً | `behavior/migrations/0013_encrypt_sensitive_text.py` SQL خامٌ صحيحٌ بـ`encrypt_field` وحارسِ تكرار؛ القاعدةُ: كلُّ قيمةٍ تمرّ بـ`encrypt_field` |
| 17 | ثلاثيّةُ `national_id`/`phone` و`hmac_field` و`USERNAME_FIELD` | صحيح، ناقص | `core/models/user.py`؛ ينقصه أنّ `save()` هو من يحسبها وهو لا يجري في RunPython (مختبر) |
| 18 | `AuditLog` بمديرٍ يمنع التعديل | صحيح، ناقص | استثناءُ `update(user=None)`؛ والمديرُ غائبٌ في النموذج التاريخيّ |
| 19 | «backfill يقرّر `objects` أم `all_objects`» | مضلّل | لا نموذجَ يرث `SoftDeleteModel` على main، والنموذجُ التاريخيّ بلا `all_objects` و`objects` يشمل المحذوف (مختبر) |
| 20 | «كلُّ الـPK UUID» | خاطئ | `DEFAULT_AUTO_FIELD = BigAutoField`؛ جداولُ رقميّة (`core/migrations/0035_storedfile.py`، `developer_feedback`) |
| 21 | النشرُ المتدحرج بـ`docker compose up`/gunicorn | قديم | Railway `preDeploy` ثمّ `start` (`.railway/railway.ts`)، daphne (`Procfile`)؛ gunicorn أُزيل (`requirements.txt`) |
| 22 | «>300ms ← مهمّةٌ خلفيّة حسب معايير المشروع» | صحيحٌ بمصدرٍ آخر | «القرارات الهندسيّة» في `~/.claude/CLAUDE.md` لا `CLAUDE.md` المستودع |
| 23 | «جرّب على نسخةٍ من بيانات الإنتاج» | غيرُ موثَّق | لا مسارَ في المستودع لنسخ الإنتاج محلّيّاً؛ قواعدُ الجلسات مبذورة — حُذف |
| 24 | بعد الترحيل: `collectstatic` ورفعُ `?v=` في `base.html`/`login.html` | قديم | `CLAUDE.md` «كسرُ ذاكرة المتصفّح — لا تفعل شيئاً»؛ لا collectstatic في التطوير |
| 25 | `ENCRYPTED_MODELS = {healthrecord, customuser}` | قديم | ستّةٌ على main: + behaviorinfraction، clinicvisit، schoolbus، studentnote — صار يُستخرج حيّاً |
| 26 | السكربت على ويندوز | عطل | `UnicodeEncodeError` (cp1256) قبل أيّ نتيجة، و`relative_to` يسقط لملفٍّ خارج الجذر |

## التغييرات
| البند | القديم | الجديد | السبب | الدليل |
|---|---|---|---|---|
| الوصف | عربيٌّ فقط، بلا «ليست لـ» | ثنائيٌّ pushy بعبارات CI (`lintmigrations`، `db_default`، Conflicting migrations) وما ليس لها | الكرّاسة §2 | — |
| البنية | SKILL 108 بلا مراجع ولا حالات | SKILL 54 + أربعةُ مراجع + `99-test-cases.md` | الكرّاسة §2 | — |
| بوّابة CI | غائبة | `00-policy-and-ci.md`: الوظيفة وخطواتها، وجدولُ ما يُسقطه المدقّق مُختبَراً | سببُ سقوط الطلبات الأوّل | `quality-gate.yml`، المختبر |
| `db_default` | غائب | قاعدةٌ وفخّ وسابقة | يمنع سقوطَ النسخة القديمة والبوّابة | المختبر، `operations/…/0053` |
| النموذجُ التاريخيّ | غائب | قاعدةٌ ومرجعٌ مع ما أثبته المختبر | أخطرُ فخّ في تعبئة PII | المختبر، `core/…/0020` |
| الجلساتُ المتوازية | «لا worktrees» | `03-parallel-sessions.md`: `$DC`، القاعدةُ المتأخّرة، تعارضُ الترقيم، المسوّدةُ المطبَّقة | الواقعُ منذ 09-08 | `CLAUDE.md`، إيداع `a213d3c7`، ذاكرتا `feedback_migrate_after_session_db` و`feedback_local_roadmap_db_drift` |
| هجراتُ الخارطة | غائب | خارجَ نطاق الجلسات | الترقيمُ يتصادم | `CLAUDE.md` |
| السكربت | AST ساذج + فحصُ SQL وهميّ | AST يقرأ الوسائط الموضعيّة و`atomic` صنفاً وM2M و`db_default` و`SeparateDatabaseAndState`؛ `--sql` لأيّ ملفّ يصنّف الجمل ويمرّرها على محلّل المدقّق؛ `--sql-stdin`، `--since`؛ نماذجُ مشفّرةٌ حيّة؛ UTF-8 | البنود 4–13، 25، 26 | اختباراتٌ أدناه |
| الشدّة | 128 🔴 من 301 هجرةً على main | 61 🔴 (أغلبُها هجراتٌ قديمةٌ هدّامةٌ سبقت البوّابة) | 🔴 يجب أن يعني شيئاً | تشغيلٌ على كلّ هجرات main |

## اختبارُ السكربت
- 15 حالةً اصطناعيّة (الجدول في `references/99-test-cases.md`): الأصلُ (بعد تجاوز سقوطه بالترميز بـ`PYTHONIOENCODING`) خالف المتوقَّعَ في 11 (إنذاراتٌ كاذبة في M2M وRunPython الموضعيّ وAlterField والجدول الجديد والخلط، وصمتٌ عن `atomic` في تعليقٍ وعن `SeparateDatabaseAndState`، وتهوينٌ لـ`default=` بلا `db_default` وللقيد الفريد، وتهويلٌ لـ`db_default`)، وطبع `RenameModel «»` بلا اسم؛ الجديدُ طابقها كلَّها.
- داخل الصورة على مشروعٍ مختبريّ: `--app labapp --since 0002 --sql` أظهر «[مدقّق CI] خطأ: NOT_NULL» لـ`default=` وحده، وALTER_COLUMN وADD_UNIQUE، وتحذير CREATE_INDEX — مطابقاً لـ`lintmigrations` على الملفّات نفسِها. ورمزُ الخروج 1؛ و`--sql-stdin` على هجرة `db_default` أعطى 0.
- لم يُترك في التسليم `__pycache__` ولا ملفٌّ مؤقّت.

## يحتاج قرارَ المالك أو تأكيدَه
1. **فرقُ إصدار المدقّق:** CI يثبّت `django-migration-linter==5.2.0` و`requirements-dev.txt`/الصورة 6.0.0. جدولُ «ما يُسقطه» اختُبر بـ6.0.0 فقط. أيُّهما المعتمد؟ (تنزيلُ 5.2.0 للتحقّق لم يُجرَ.)
2. **README وDEPLOYMENT-RAILWAY يقولان PostgreSQL 16** والإنتاجُ 18 بحسب `backup.yml` — يؤكّده المالك من لوحة Railway، وتُصحَّح الوثيقتان في طلبٍ منفصل.
3. **صرامةُ الحارس فوق البوّابة:** RunPython/RunSQL بلا عكس 🔴 في الحارس وتحذيرٌ فقط في CI. أُبقيت أشدّ (فشلُ نشرٍ بلا عكسٍ إصلاحٌ يدويّ). هل يُرفع إلى CI (`--warnings-as-errors` أو فحصٌ مخصّص)؟
4. **أحجامُ جداول الإنتاج** غيرُ متاحةٍ لجلسة: قائمةُ «الجداول المرجَّح كبرُها» استدلال. قائمةٌ رسميّةٌ بالأحجام (أو عتبة) تجعل 🟠 قراراتٍ لا تقديرات.
5. **`SET NOT NULL` في خطوة التقليص** تُسقطه البوّابة دائماً (NOT_NULL). هل يبقى عمودٌ «مرّ بتوسيعٍ» `null=True` + `db_default` للأبد، أم يُعتمد مسارُ استثناءٍ مسمّى كما فُعل لـ`StaffEvaluation`؟
6. أمرُ `lintmigrations app name` بإعدادات `testing` داخل حاوية جلسةٍ حقيقيّة لم يُجرَّب (جُرّب في المختبر فقط).
