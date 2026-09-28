# دليلُ العمليّات: الخطر والبديل

متى تقرأ هذا الملف: حين يعلّم الحارسُ عمليّةً بـ🔴 أو 🟠 وتريد البديلَ المعتمد، أو تراجع هجرةً لغيرك سطراً سطراً.

«البوّابة» = حكمُ django-migration-linter 6.0.0 كما اختُبر (`references/00-policy-and-ci.md`). والأقفالُ من وثائق PostgreSQL (`ALTER TABLE`، `CREATE INDEX`).
الجداولُ التي يُرجَّح كبرُها (حضورٌ، حصص، درجات، تسجيل، إشعارات، سجلُّ التدقيق، المستخدمون) استدلالٌ من طبيعتها؛ أحجامُ الإنتاج الفعليّة لا تُقرأ من جلسة.

## إضافة
| العمليّة | ما يحدث | البوّابة | البديل |
|---|---|---|---|
| `AddField(null=True)` | عمودٌ بلا افتراض، metadata | سليم | — |
| `AddField(default=X)` بلا `db_default` | يضيف ثمّ `DROP DEFAULT` ← كتابةُ القديم تسقط | 🔴 NOT_NULL | `default=X, db_default=X` (السابقة `operations/migrations/0053_excuse_review.py`) |
| `AddField(default=X, db_default=X)` | الافتراضُ يبقى في القاعدة | سليم | — |
| `AddField` إلزاميّ بلا أيّ افتراض | يسقط على جدولٍ فيه صفوف | 🔴 NOT_NULL | `null=True` ← تعبئة ← قرارُ التقليص |
| `AddField(default=callable)` | القيمةُ تُحسب مرّةً لكلّ الصفوف (مُثبَت) | 🔴 إن اقترن بـ`unique` | `null=True` ← تعبئةٌ لكلّ صفّ ← القيد |
| `AddField(ForeignKey)` | عمودٌ + فهرس + قيدُ مفتاحٍ يفحص الجدول | 🟠 (متوقَّعٌ CREATE_INDEX؛ لم يُختبر) | على جدولٍ كبير: `db_index=False` ثمّ `AddIndexConcurrently` |
| `AddField(unique=True)` | قيدٌ فريد بقفلٍ حاجز | 🔴 ADD_UNIQUE | عمودٌ عاديّ ← تعبئة ← فهرسٌ فريدٌ متزامن ← قرارُ مراجعة |
| `AddField(ManyToManyField)` | جدولٌ وسيطٌ جديد | سليم | — |
| `CreateModel` (+ قيودُه في الملفّ نفسِه) | جدولٌ فارغ | سليم | — |

## فهارس وقيود
| العمليّة | القفل | البوّابة | البديل |
|---|---|---|---|
| `AddIndex` | SHARE: يمنع الكتابة طوال البناء | 🟠 CREATE_INDEX | `AddIndexConcurrently` + `atomic = False` في ملفٍّ وحدَه (السابقة `operations/migrations/0055_attendance_exit_partial_index.py`) |
| `AddIndexConcurrently` بلا `atomic = False` | يفشل: CONCURRENTLY لا يجري في معاملة | 🔴 (الحارس) | أضِف `atomic = False` في صنف Migration |
| `AddConstraint(UniqueConstraint)` / `AlterUniqueTogether` | ACCESS EXCLUSIVE + فحصُ الجدول | 🔴 ADD_UNIQUE | يُقرَّر في المراجعة؛ الأخفُّ فهرسٌ فريدٌ متزامن |
| `AddConstraint(CheckConstraint)` | فحصُ الجدول كلِّه بقفل | لم يُختبر | `NOT VALID` ثمّ `VALIDATE CONSTRAINT` في هجرةٍ لاحقة (RunSQL داخل `SeparateDatabaseAndState`) |

## تعديل
| العمليّة | ما يحدث | البوّابة | البديل |
|---|---|---|---|
| `AlterField` على `verbose_name`/`help_text`/`choices` | `-- (no-op)` | سليم | — |
| `AlterField` يغيّر النوع أو الطول | `ALTER COLUMN TYPE` (قد يعيد كتابة الجدول) | 🔴 ALTER_COLUMN | عمودٌ جديد ← تعبئة ← تحويل ← حذفٌ لاحق |
| `AlterField` يجعله إلزاميّاً | `SET NOT NULL`: فحصٌ بقفل، ويكسر كتابةَ القديم | 🔴 NOT_NULL | ابقِه `null=True` مع `db_default`، والتقليصُ قرارُ مراجعة |
| `AlterField` إلى `EncryptedTextField` | من `TextField` لا SQL (الحقلُ نصٌّ في القاعدة)، ومن `CharField` تغييرُ نوعٍ إلى `text`؛ وفي الحالين القيمُ القديمة صريحة | حسب `--sql` | هجرةُ بياناتٍ تشفّر القديم (السابقة `behavior/migrations/0013_encrypt_sensitive_text.py`) |

## حذف وإعادة تسمية
`RemoveField`، `DeleteModel`، `RenameField`، `RenameModel`، `AlterModelTable`: 🔴 دائماً — الشيفرةُ المنشورة تقرأ القديم. خطوةُ «تقليص» في إصدارٍ لاحق فقط (`references/00-policy-and-ci.md`).
و`SeparateDatabaseAndState`: ما في `database_operations` يُفحص كأيّ عمليّة؛ و`state_operations` لا يلمس القاعدة. السوابقُ الخمس على main في `0001_initial` لتطبيقاتٍ نُقلت نماذجُها بين التطبيقات (مثلاً `library/migrations/0001_initial.py`، `core/migrations/0008_remove_moved_models.py`).

## بيانات
| العمليّة | القاعدة |
|---|---|
| `RunPython(f)` بلا عكس | 🔴 في الحارس (البوّابة تحذّر فقط): `RunPython(f, back)` أو `RunPython.noop` صراحةً |
| `RunSQL(sql)` بلا `reverse_sql` | 🔴 كذلك |
| مخطّطٌ + بيانات في ملفٍّ واحد | 🟠 وثائق Django: على PostgreSQL تجري الهجرةُ في معاملةٍ واحدة، وقد تسقط بـ`pending trigger events`. على main سوابقُ مختلطةٌ مرّت (`behavior/migrations/0013_…`)، فالفصلُ أسلمُ لا شرط |
التفصيل في `references/02-data-migrations.md`.

## قراءةُ مخرج الحارس
- 🔴 = يمنع الدفع (رمزُ الخروج 1): إمّا البوّابةُ ستسقط، أو هدمٌ/فقدٌ/فشلُ تشغيل.
- 🟠 = قرّر بحجم الجدول، واذكر قرارك في وصف الطلب.
- «[مدقّق CI] …» = سطرٌ من محلّل البوّابة نفسِه على SQL هجرتك؛ لا يظهر إلّا مع `--sql` وحيث الحزمةُ مثبّتة (حاوية الجلسة).
- على كلّ هجرات main (301 ملفّاً، 2026-09-28) يعطي الحارسُ 103 سليماً و137 🟠 و61 🔴 — أغلبُ الـ🔴 هجراتٌ قديمةٌ سبقت البوّابة (`0001_initial` وحذوفٌ قبل P4-1). الفحصُ للجديد لا للتاريخ.

## أنماطٌ مضادّة
- قراءةُ 🟠 على `AlterField` حكماً بالخطر دون `--sql` — كثيرٌ منها `(no-op)`.
- «الجدولُ صغيرٌ عندي» دليلاً على أنّ الفهرس لا يقفل في الإنتاج.
- `RunPython.noop` عكساً لهجرةٍ تحذف بيانات دون أن تقول في التعليق إنّ التراجع لا يعيدها.
- إضافةُ `unique=True` و`db_index=True` معاً على حقلٍ جديدٍ في جدولٍ قائم «احتياطاً».
