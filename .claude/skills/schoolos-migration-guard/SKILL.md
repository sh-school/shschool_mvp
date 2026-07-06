---
name: schoolos-migration-guard
description: |
  حارس أمان ترحيلات Django في SchoolOS (Django 5.2 + PostgreSQL 16). يفحص أي migration
  قبل تطبيقه على قاعدة بيانات فيها بيانات حقيقية: الأقفال الحاجزة (ACCESS EXCLUSIVE)،
  فقد البيانات، كسر التوافق الرجعي مع الكود القديم أثناء النشر المتدحرج، الأعمدة NOT NULL
  بلا default، RunPython بلا reverse، والفهارس/القيود على جداول كبيرة بلا CONCURRENTLY.
  استخدمها دائماً وتلقائياً عند: إنشاء migration جديد، مراجعة migration قبل الدمج أو النشر،
  ظهور "makemigrations"/"migrate"، تعديل أي models.py، أو السؤال "هل هذا الترحيل آمن؟".
  Trigger on: migration, makemigrations, migrate, schema change, ALTER TABLE, "هل الترحيل آمن".
---

# حارس ترحيلات SchoolOS

> الهدف: **صفر توقّف وصفر فقد بيانات** عند النشر على قاعدة إنتاج فيها آلاف السجلات.
> هذه المنصة حكومية قطرية — الترحيل الخاطئ = تعطّل مدرسة + مخاطرة PDPPL على سجلات مشفّرة.

المسار الوحيد للعمل: `D:\shschool_mvp` مباشرة. لا تعدّل في worktrees.

---

## 1. الخطوة الأولى دائماً — شغّل الفاحص

```bash
python .claude/skills/schoolos-migration-guard/scripts/check_migration.py --app <app_label>
# أو لكل الترحيلات غير المطبّقة:
python .claude/skills/schoolos-migration-guard/scripts/check_migration.py --pending
# لفحص ملف محدد:
python .claude/skills/schoolos-migration-guard/scripts/check_migration.py --file operations/migrations/0017_xxx.py
```

الفاحص يفعل:
1. `makemigrations --check --dry-run` — يكشف الـ models المعدّلة بلا migration.
2. تحليل AST ثابت لكل عملية داخل `operations = [...]` وتصنيف خطورتها.
3. عند توفّر قاعدة اختبار: `sqlmigrate` لاستخراج الـ SQL الفعلي وكشف الأقفال الحاجزة.

اقرأ تقرير الفاحص، ثم راجع البنود أدناه يدوياً لأنّ التحليل الثابت لا يرى حجم الجدول.

---

## 2. سلّم الخطورة — ماذا يعني كل تصنيف

### 🔴 حرج — يوقف قاعدة الإنتاج أو يفقد بيانات

| النمط | لماذا خطر | البديل الآمن |
|------|-----------|--------------|
| `AddField(null=False)` بلا `default` على جدول غير فارغ | PostgreSQL يعيد كتابة الجدول + قفل ACCESS EXCLUSIVE | أضِف العمود `null=True` أولاً → عبّئ بيانات في migration منفصل → migration ثالث يجعله `NOT NULL` |
| `RemoveField` / `DeleteModel` | فقد بيانات لا رجعة فيه + يكسر الكود القديم أثناء النشر المتدحرج | **مرحلتان**: (1) أوقف استخدام الحقل في الكود وانشر، (2) احذفه في إصدار لاحق |
| `RenameField` / `RenameModel` | الكود القديم يقرأ الاسم القديم أثناء النشر → 500 على مستخدمين أحياء | أضِف الحقل الجديد + انسخ + أوقف القديم تدريجياً (لا تعِد التسمية مباشرة) |
| `AlterField` يغيّر النوع (مثلاً `CharField→UUIDField`) | إعادة كتابة الجدول + قفل طويل + قد يفشل التحويل | عمود جديد + backfill بـ Celery + تبديل |
| `RunPython` بلا `reverse_code` | لا يمكن التراجع (`migrate <app> <prev>`) عند فشل النشر | مرّر `reverse_code`؛ إن تعذّر استخدم `migrations.RunPython.noop` صراحةً وبرّر ذلك |
| خلط تعديل schema **و** تعبئة بيانات في نفس الملف | الـ RunPython يقفل صفوفاً أثناء تعديل البنية → تعارض أقفال | افصل: ملف للـ schema، ملف للبيانات |

### 🟠 تحذير — يقفل الجدول مؤقتاً على PostgreSQL

| النمط | العلاج على PostgreSQL 16 |
|------|--------------------------|
| `AddIndex` على جدول كبير | استخدم `AddIndexConcurrently` (من `django.contrib.postgres.operations`) + `atomic = False` في الـ Migration |
| `AddConstraint` (UNIQUE/CHECK/FK) | أنشئه `NOT VALID` ثم `VALIDATE CONSTRAINT` في migration لاحق (عبر `SeparateDatabaseAndState` أو SQL يدوي) |
| `unique=True` على حقل موجود | يبني فهرساً فريداً بقفل — نفس علاج الفهرس المتزامن |
| `AlterField` يضيف `db_index=True` | فهرس بقفل — استخدم الإنشاء المتزامن |

### 🟢 آمن — عمليات metadata فقط (لا تلمس الصفوف)

`AddField(null=True)` بلا default، تغيير `verbose_name`/`help_text`/`choices`، `AlterModelOptions`، `AlterOrderWithRespectTo` الفارغ، إضافة model جديد فارغ.

---

## 3. قواعد SchoolOS الخاصة (لا تكسرها)

- **الحقول المشفّرة**: أي حقل يستخدم `core.fields.EncryptedTextField` أو يُشفّر عبر `encrypt_field` (انظر `core/models/_crypto.py`) — **ممنوع** عمل data migration يقرأ/يكتب قيمته الخام بـ raw SQL؛ استخدم الـ ORM حتى يمرّ عبر `from_db_value`/`get_prep_value`. تعبئة بـ SQL مباشر تخزّن نصاً صريحاً وتكسر PDPPL.
- **`national_id` / `phone`**: لها ثلاثية (خام + `_encrypted` + `_hmac`). أي migration يمسّها يجب أن يعيد حساب الـ HMAC عبر `hmac_field` وإلا ينكسر تسجيل الدخول (USERNAME_FIELD = national_id).
- **جداول immutable**: `AuditLog` في `core/models/audit.py` له manager يمنع UPDATE/DELETE. لا تكتب migration يعدّل صفوفه.
- **`SchoolScopedModel` / `SoftDeleteModel`**: عند إضافة FK جديد إلى model موجود، انتبه أنّ `all_objects` يشمل المحذوف soft-deleted — أي backfill يجب أن يقرر صراحةً `objects` أم `all_objects`.
- **UUID PK**: كل الـ PK من نوع UUID (`TimeStampedModel`). لا تفترض PK رقمياً في أي RunPython.

---

## 4. النشر المتدحرج (Rolling Deploy) — القاعدة الذهبية

الكود القديم والجديد يعملان **معاً** لثوانٍ أثناء `docker compose up`/إعادة تشغيل gunicorn. لذلك كل migration يجب أن يكون **متوافقاً في الاتجاهين**: الكود القديم يجب ألا ينكسر بالمخطّط الجديد، والعكس. هذا يفرض نمط "التوسّع ثم الانكماش" (expand/contract):

1. **Expand**: أضِف الجديد (عمود/جدول) `null=True`، انشر الكود الذي يكتب في القديم والجديد.
2. **Migrate data**: عبّئ الجديد من القديم عبر أمر إدارة أو مهمة Celery (لا داخل migration إن كان الجدول ضخماً — العملية >300ms تذهب لـ background job حسب معايير المشروع).
3. **Contract**: بعد التأكد، اجعل الحقل `NOT NULL`/احذف القديم في إصدار **لاحق**.

---

## 5. قائمة تحقّق قبل الموافقة على أي migration

- [ ] الفاحص الآلي مرّ بلا 🔴.
- [ ] `sqlmigrate` لا يُظهر `ACCESS EXCLUSIVE` على جدول كبير (attendance, grades, audit_log, sessions).
- [ ] كل `RunPython` له `reverse_code` (أو `noop` مبرّر).
- [ ] لا خلط schema + data في ملف واحد.
- [ ] الحقول المشفّرة تُعبّأ عبر ORM لا SQL.
- [ ] متوافق رجعياً مع الكود المنشور حالياً (expand/contract).
- [ ] جُرّب على نسخة من بيانات الإنتاج، وقيس زمن التنفيذ.
- [ ] خطة تراجع مكتوبة: `python manage.py migrate <app> <prev_number>`.

## 6. بعد الترحيل

```bash
python manage.py migrate --plan        # عاين قبل التنفيذ
python manage.py migrate
python manage.py makemigrations --check # تأكد لا توجد فروق متبقية
```

عند تعديل static (CSS/JS) ضمن نفس الـ PR: `python manage.py collectstatic --noinput` ثم ارفع رقم الإصدار في `base.html`/`login.html` (cache-busting).
