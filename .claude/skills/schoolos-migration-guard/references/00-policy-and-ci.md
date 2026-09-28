# السياسة وبوّابة CI

متى تقرأ هذا الملف: قبل هجرةٍ تحذف أو تعيد التسمية أو تجعل عموداً إلزاميّاً، أو حين تسقط وظيفةُ «مدقّق الهجرات — Expand/Contract» في CI وتريد معرفةَ ما تفحصه وكيف تُعيد إنتاجها محلّيّاً.

## لماذا «توسيعٌ ثمّ تقليص»
الشيفرةُ القديمة والمخطّطُ الجديد يلتقيان دائماً في ثلاثة مواضع:
1. **النشر:** `preDeploy` (`bash scripts/railway-predeploy.sh`) يشغّل `migrate --noinput` مرّةً قبل أن تستقبل النسخةُ الجديدة الحركة، والنسخةُ السابقة وعاملُ Celery ما زالا يخدمان على المخطّط الجديد حتّى تحلّ محلَّهما (المصدر: `.railway/railway.ts` — `preDeploy` ثمّ `start`؛ `Procfile`). والتراجعُ عن نشرٍ يُعيد شيفرةً قديمةً فوق مخطّطٍ جديد.
2. **الجلسات المتوازية:** كلُّ شجرةِ عملٍ على شيفرتها وقاعدتها (منذ حادثة 2026-09-11)، لكنّها تأخذ هجراتِ main حين تندمج.
3. **الخادم:** daphne لا gunicorn (المصدر: `Procfile`، `Dockerfile`) — ولا فرقَ هنا: كلُّ طلبٍ تخدمه النسخةُ القديمة يرى المخطّطَ الجديد.

فكلُّ هجرةٍ يجب أن تعمل مع الشيفرة السابقة واللاحقة معاً. والهدّامُ ينقسم:

| الغرض | الإصدار 1 (توسيع) | الإصدار 2 (تقليص، بعد أن يستقرّ الأوّل) |
|---|---|---|
| حذفُ عمود/نموذج | أوقف كلَّ قراءةٍ وكتابةٍ له في الشيفرة وانشر | `RemoveField`/`DeleteModel` |
| إعادةُ تسمية عمود | أضِف الجديد، اكتب في الاثنين، املأ الجديد، حوِّل القراءة | احذف القديم |
| عمودٌ إلزاميٌّ جديد | `default=` + `db_default=` (يمرّ مباشرةً) — أو `null=True` ثمّ املأ | `SET NOT NULL` إن لزم (تُسقطه البوّابة ← قرارُ مراجعة) |
| تغييرُ نوع عمود | عمودٌ جديدٌ بالنوع الجديد + تعبئة + تحويلُ القراءة | احذف القديم |

السابقةُ الموثّقة: حذفُ `operations.StaffEvaluation` خطوتان — #417 أوقف كلَّ قارئٍ وكاتبٍ وعدُّ الإنتاج صفر، ثمّ هجرةُ الحذف (المصدر: التعليق فوق `MIGRATION_LINTER_OPTIONS` في `shschool/settings/testing.py`، وADR-0002 §4).

## البوّابة كما هي في الشيفرة
- الوظيفة: `migration-linter` في `.github/workflows/quality-gate.yml` (اسمُها المعروض «مدقّق الهجرات — Expand/Contract»)، على PostgreSQL 16.
- الخطوات: اختبارُ الوصل `tests/test_migration_linter_wiring.py` ← `migrate --noinput` ← `python manage.py lintmigrations --git-commit-id "$BASE_SHA"` (أساسُ طلب الدمج أو طابور الدمج) — فلا تُفحص إلّا الهجراتُ الجديدة منذ الأساس.
- التسجيل: `django_migration_linter` يُضاف إلى `INSTALLED_APPS` في `shschool/settings/testing.py` فقط إن كانت الحزمةُ مثبّتة.
- الاستثناءُ الوحيدُ القائم مسمّى باسم هجرته (`MIGRATION_LINTER_OPTIONS`)، وكلُّ استثناءٍ جديدٍ قرارٌ يُسأل عنه في مراجعة الطلب (المصدر: `CLAUDE.md`).
- وفي وظيفة الاختبارات أيضاً: `python manage.py makemigrations --check --noinput` — نموذجٌ عُدّل بلا هجرةٍ يُسقطها (المصدر: `quality-gate.yml`، و`deploy-railway.yml`).

## ما يُسقطه المدقّق فعلاً (مُختبَر)
مختبرٌ معزول (Django 5.2.17، PostgreSQL 18، django-migration-linter 6.0.0 من صورة الحاوية)، `sqlmigrate` ثمّ `lintmigrations` لكلّ حالة، 2026-09-28:

| الحالة | SQL المولَّد (مختصر) | حكمُ المدقّق |
|---|---|---|
| `AddField(... default="")` بلا `db_default` | `ADD COLUMN … DEFAULT '' NOT NULL;` ثمّ `ALTER COLUMN … DROP DEFAULT;` | خطأ NOT_NULL |
| `AddField(... default="", db_default="")` | `ADD COLUMN … DEFAULT '' NOT NULL;` | سليم |
| `AddField(UUIDField(default=uuid.uuid4))` | `DEFAULT '<uuid ثابت>'::uuid NOT NULL` ثمّ `DROP DEFAULT` | خطأ NOT_NULL (والقيمةُ واحدةٌ لكلّ الصفوف) |
| `AlterField` يغيّر `verbose_name` وحده | `-- (no-op)` | سليم |
| `AlterField` يوسّع `max_length` 50←80 | `ALTER COLUMN … TYPE varchar(80);` | خطأ ALTER_COLUMN (ولو كان آمناً فعليّاً) |
| `AddConstraint(UniqueConstraint)` على جدولٍ قائم | `ADD CONSTRAINT … UNIQUE` | خطأ ADD_UNIQUE |
| `AddIndex` | `CREATE INDEX …` | تحذير CREATE_INDEX (لا يُسقط) |
| `RunPython(fwd)` بلا عكس | — | تحذير «not reversible» (لا يُسقط) |
| `AddField(ManyToManyField)` | `CREATE TABLE` للجدول الوسيط + قيوده | سليم |

وحذفُ العمود والجدول وإعادةُ تسمية العمود وNOT NULL بلا افتراض يثبتها `tests/test_migration_linter_wiring.py` نفسُه.
الحارسُ (`scripts/check_migration.py --sql`) يستدعي المحلّلَ نفسَه على SQL هجرتك، فيطابق هذا الجدولَ دون `--git-commit-id`.

## إعادةُ إنتاج البوّابة محلّيّاً
- الأسهل: `check_migration.py --file <…> --sql` داخل حاوية جلستك (يستعمل قاعدة جلستك لـ`sqlmigrate`، ومحلّلُ المدقّق مثبّتٌ في الصورة).
- الأمرُ نفسُه الذي في CI يحتاج إعدادات `testing` وقاعدةً مطبّقةً وتاريخَ غيت؛ داخل الحاوية لا يُعتمد على غيت الشجرة (ملفُّ `.git` فيها يشير إلى مسار ويندوز). فاستعمل الصيغةَ بلا غيت: `lintmigrations <app> <migration_name>` بإعدادات `testing` مع `TEST_DB_*` مأخوذةً من `DB_*` كما في أمر الاختبار في `CLAUDE.md`. (لم يُجرَّب هذا الشكلُ في حاوية جلسةٍ حقيقيّة؛ جُرّب `lintmigrations app name` في المختبر.)
- **فرقُ إصدار:** CI يثبّت `django-migration-linter==5.2.0` صراحةً، و`requirements-dev.txt` والصورةُ على 6.0.0. الجدولُ أعلاه من 6.0.0.

## إصداراتُ القاعدة
- الإنتاج: PostgreSQL 18 (المصدر: تعليقُ `.github/workflows/backup.yml` «خادم الإنتاج الفعلي PostgreSQL 18»).
- التطوير المحلّيّ: `postgres:18-alpine` (`docker-compose.yml`). CI وnightly: `postgres:16-alpine`.
- `README.md` و`DEPLOYMENT-RAILWAY.md` ما زالا يقولان 16 — قديم.
- لا فرقَ بينهما في ما يعنينا هنا: إضافةُ عمودٍ بافتراضٍ ثابتٍ بلا إعادة كتابةٍ منذ 11، و`CREATE INDEX CONCURRENTLY` و`NOT VALID` قائمةٌ في الاثنين.

## أنماطٌ مضادّة
- حذفُ السطر المخالف من الهجرة «لتمرّ البوّابة» وتركُ النموذج مختلفاً — `makemigrations --check` يُسقطها، والمخطّطُ ينحرف.
- «سأحذف العمودَ والشيفرةَ في الطلب نفسِه، فلا أحد يقرؤه بعد الدمج» — النسخةُ المنشورة تقرؤه حتّى تُستبدل، والأشجارُ الأخرى كذلك.
- الاعتمادُ على نجاح الهجرة في قاعدة جلستك دليلاً على الأمان — قاعدتُك صغيرةٌ ومبذورة، والقفلُ يظهر على جداول الإنتاج.
- نسخُ «PostgreSQL 16» من README إلى قرارٍ يخصّ الإنتاج.
