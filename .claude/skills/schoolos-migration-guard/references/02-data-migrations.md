# هجراتُ البيانات: RunPython وRunSQL

متى تقرأ هذا الملف: حين تكتب هجرةً تملأ عموداً أو تنقل بياناتٍ أو تشفّر قيماً قديمة، أو تراجع هجرةً فيها `apps.get_model`.

## النموذجُ التاريخيّ ليس نموذجَك
داخل `RunPython` تعطيك `apps.get_model("app", "Model")` صنفاً مبنيّاً من حالة الهجرات: الحقولُ نفسُها (بأصنافها الحقيقيّة، فـ`EncryptedTextField` يشفّر ويفكّ)، لكن بلا دوالّ النموذج وبلا مديراتٍ مخصّصة إلّا ما عليه `use_in_migrations = True` (وثائق Django: «Historical models»؛ ولا مديرَ في المشروع عليه هذه الراية — بحثٌ في main).
مُثبَتٌ في مختبرٍ (Django 5.2.17، 2026-09-28) بنموذجٍ له `save()` مخصّص ومديرٌ يستبعد المحذوف:
- `hasattr(Model, "all_objects")` ← False.
- `Model.objects.count()` عدّ الصفَّ المحذوفَ ناعماً أيضاً (المديرُ المخصّصُ لم يُطبَّق).
- `Model.objects.create(...)` لم يشغّل `save()` المخصّص.

ما يعنيه في SchoolOS:
- **ثلاثيّةُ `national_id` و`phone`** في `core/models/user.py`: `CustomUser.save()` هو من يحسب `*_encrypted` و`*_hmac`. في RunPython لا يجري، فاحسبهما بـ`encrypt_field`/`hmac_field` من `core.models.crypto` صراحةً، وإلّا بقي الـHMAC قديماً فينكسر البحثُ والتفرّد (`national_id` هو `USERNAME_FIELD`).
- **المديراتُ والدوالّ المخصّصة** (`.live(school, year=…)` في `YearScopedQuerySet` وأمثالها) غائبة: اكتب الفلترَ صريحاً. و`SoftDeleteModel` لا يرثه اليوم نموذجٌ على main، فإن ظهر فتذكّر أنّ `objects` التاريخيّ يشمل المحذوف.
- **`AuditLog`** (`core/models/audit.py`) يمنع التعديلَ والحذفَ عبر مديره `_ImmutableQuerySet` — إلّا فصلَ هويّة الفاعل `update(user=None)` للمحو. المديرُ غائبٌ في النموذج التاريخيّ، فهجرةٌ تلمس صفوفه لا يوقفها شيء: لا تكتب هجرةً تعدّله أبداً.
- **المفتاحُ الأساسيّ:** الغالبُ UUID (`TimeStampedModel` و`id = UUIDField` صريحةٌ في أكثر النماذج)، لكنّ `DEFAULT_AUTO_FIELD = BigAutoField` وبعضُ الجداول رقميّة (`core/migrations/0035_storedfile.py`، `developer_feedback/migrations/0001_initial.py`). اقرأ `Model._meta.pk` ولا تفترض.

## الحقولُ المشفّرة
النماذجُ التي فيها `EncryptedTextField` أو عمودُ `*_encrypted` (يستخرجها الحارسُ حيّاً من الشيفرة؛ على main 2026-09-28): `BehaviorInfraction`، `ClinicVisit`، `CustomUser`، `HealthRecord`، `SchoolBus`، `StudentNote`.

نمطان صحيحان على main:
1. **عبر ORM مع حسابٍ صريح** — `core/migrations/0020_populate_national_id_hmac_encrypted.py`: دفعاتٌ من 500، و`hmac_field`/`encrypt_field` لكلّ صفّ، ثمّ `bulk_update` بالأعمدة المحسوبة.
2. **SQL خامٌ مع حارسٍ من التشفير المزدوج وعكسٍ حقيقيّ** — `behavior/migrations/0013_encrypt_sensitive_text.py`: يقرأ بالـcursor، ويفكّ أوّلاً (`decrypt_field(v) == v` يعني صريحاً)، ويشفّر الصريحَ وحده، والعكسُ يفكّ.

الخطرُ الذي يُتّقى: كتابةُ نصٍّ صريحٍ في عمودٍ يُفترض أنّه مشفّر (خرقٌ لـPDPPL)، أو تشفيرُ المشفّر مرّتين. فالقاعدة: SQL خامٌ مسموحٌ **فقط** إذا مرّت كلُّ قيمةٍ بـ`encrypt_field` في بايثون قبل الكتابة، بحارسٍ من التكرار. وتصنيفُ «هل يُشفَّر الحقلُ الجديد أصلاً» لمهارة pdppl-pii-audit.
وفي التطوير بلا `FERNET_KEY` يعيد `encrypt_field` القيمةَ كما هي (fail-open في DEBUG) — فنجاحُ هجرتك محلّيّاً لا يثبت أنّها شفّرت؛ الإنتاجُ fail-closed (`core/models/crypto.py`).

## الحجمُ والتوقيت
- تعبئةُ جدولٍ كبير داخل هجرةٍ تطيل `preDeploy` وتمسك الأقفالَ طوالها. القاعدةُ العامّة للمالك: ما يزيد عن 300ms مهمّةٌ خلفيّة (`~/.claude/CLAUDE.md`، القرارات الهندسيّة).
- البديلُ القائم في المشروع: أمرُ إدارةٍ idempotent يُشغَّل بعد النشر — `core/management/commands/populate_phone_encryption.py`، `repair_pii_columns.py`. وتشغيلُه على الإنتاج بيد المالك أو جلسة النشر لا بيد جلسة التطوير.
- الهجرةُ نفسُها تبقى صغيرة: توسيعُ المخطّط، ثمّ الأمرُ يملأ، ثمّ (إن لزم) تقليصٌ في إصدارٍ لاحق.

## العكس
- `RunPython(forward, backward)` بالموضع أو `reverse_code=` — كلاهما صحيح، والحارسُ يقرأ الاثنين.
- `migrations.RunPython.noop` مقبولٌ حين لا معنى للعكس (تعبئةُ عمودٍ جديدٍ يُحذف بعكس المخطّط)، مع تعليقٍ بالسبب. لا تكتبه لهجرةٍ تحذف أو تكتب فوق بيانات.
- `RunSQL(sql, reverse_sql=…)` أو `migrations.RunSQL.noop`.

## مخطّطٌ وبياناتٌ في ملفٍّ واحد
وثائق Django (RunPython): على قواعد تدعم معاملات DDL كـPostgreSQL تُغلَّف الهجرةُ كلُّها بمعاملة، فيُنصح بعدم خلط تغيير المخطّط وRunPython، وقد يظهر `cannot ALTER TABLE … because it has pending trigger events`. على main سوابقُ مختلطةٌ مرّت، فالحارسُ يعلّمها 🟠 لا 🔴؛ والفصلُ في ملفّين أسلم، وإجباريٌّ حين تكون التعبئةُ طويلة.

## هجراتُ الخارطة
`roadmap/migrations/` تملكها جلسةُ «خارطة التجويد» وحدها؛ ترقيمُها يتصادم إن كتبها غيرُها. أبلِغها برمز البند ورقم الطلب (المصدر: `CLAUDE.md`، «الخارطةُ الحيّة»).

## أنماطٌ مضادّة
- `from core.models import CustomUser` داخل الهجرة بدل `apps.get_model` — يربط الهجرةَ بشيفرةٍ ستتغيّر فتنكسر يوماً على قاعدةٍ جديدة.
- `Model.objects.update(field=…)` على حقلٍ يحسب `save()` مشتقّاته.
- تشفيرُ القيم دون التحقّق أنّها ليست مشفّرةً أصلاً.
- الاطمئنانُ إلى أنّ التشفير «عمل» لأنّ الهجرةَ مرّت على قاعدة التطوير.
- حلقةٌ على مئات الآلاف من الصفوف داخل `preDeploy`.
