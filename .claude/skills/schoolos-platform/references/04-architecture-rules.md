# 04 — أين أضع الكود، وما يحرسه

> متى تقرأ هذا الملف: قبل إضافة model أو service أو view أو مهمّةٍ خلفيّة أو تصديرٍ أو جدولٍ جديد، أو حين يسقط حارسُ طبقاتٍ أو حجمٍ أو تصدير.
> تفاصيلُ السقّاطات وتحديثُ خطوطها عند مهارة schoolos-quality-guards؛ والخريطةُ الكاملة `docs/governance/regression_guards.md`.

## شجرةُ القرار

| أضيف… | الموضع | ملاحظة |
|---|---|---|
| نموذجاً | `models.py` أو حزمةُ `models/` في تطبيق المجال | يرث `TimeStampedModel` أو `AuditedModel` (من أنشأ/عدّل) أو `SchoolScopedModel` من `core/models/base.py`؛ وسطرٌ في `core/tenancy.py` إن لم يحمل `school_id` |
| منطقاً أو كتابةً | `services.py` أو حزمةُ `services/` | `GradeService`، `BehaviorService`، `operations/services/*.py` نماذجُ قائمة |
| قراءةً مركّبةً لشاشة | `selectors.py` | موجودٌ في behavior وreports وstudent_affairs وstaff_affairs وnotifications وbreach وroadmap |
| استعلاماً قابلاً للسلسلة | `querysets.py` (`Model.objects.<method>()`) | مثال `core/querysets.py::UserQuerySet`، `StudentEnrollment.objects.current_of` |
| قاعدةً وزاريّةً نقيّة | `core/domain/*.py` (`grades`، `attendance`، `tones`) أو ثابتٌ في وحدة المجال (`absence_policy.py`) | بلا ORM؛ تعليقٌ يستشهد بالمادّة والصفحة |
| صفحة HTML | `views*.py` في التطبيق + `templates/<app>/` | نمطُ التخطيط من `docs/design/page_layouts.md` (مهارة web-design-mastery) |
| API | `api/` (`api/v1/`) أو `operations/api_views.py` (`api/`) | مهارة drf-endpoint-scaffold |
| عملاً فوق 300ms | `tasks.py` (Celery) | بلا اسم طابورٍ حرفيّ (انظر أدناه) |
| تصدير PDF/Excel | بنّاءٌ مسجَّلٌ في `core/exports/registry.py` من `AppConfig.ready()` | ADR-0007 |
| صلاحيّةً | مجموعةٌ في `core/permissions.py` أو قدرةٌ في `core/capabilities.py` | لا في `views*.py` |
| أمرَ إدارة | `<app>/management/commands/` | خارج نطاق mypy منذ 2026-09-26 (DBT-01) |

## قواعدُ الطبقات (`docs/architecture/layering.md`، `tests/layering_ratchet.py`)
- **دالّةُ العرض ≤ 60 سطراً و≤ 5 استدعاءاتِ ORM** — أطولُ من ذلك يُنقل إلى service. سقّاطة: العرضُ الجديدُ لا يتجاوز، والمسجَّلُ لا يزيد.
- **`request.school` لا `get_school()`** في ملفّات العروض — السقّاطةُ تعدّ مواضعَ `get_school()`.
- **`core` لا يستورد من تطبيقٍ نازل** (ADR-0004): الهدفُ خمسةُ استثناءاتٍ موضعيّة مقبولة (`academic_management`، `student_info`، `operations`، `wings`، `quality` في ملفّات الصلاحيّات والقدرات والسياق)؛ واليومَ في خطّ الأساس 12 ملفّاً (34 استيراداً) تنقص بالدفعات، وأيُّ استيرادٍ نازلٍ جديدٍ يُسقط السقّاطة. والمنسّقون العابرون للتطبيقات (المحو، الاحتفاظ) مكانُهم `governance/` لا `core/`. المصدر: `docs/governance/regression_guards.md`، `tests/layering_baseline.json`.
- **حجمُ الملفّ:** لا `.py` جديدٌ فوق 1000 سطر، والمسجَّلُ لا يكبر أكثر من 25 سطراً؛ عند التجاوز يُقسَّم **حسب المسؤوليّة** (النموذج `staff_affairs/attendance/`، وخلطاتُ mixins في `operations/services/schedule.py`). المصدر: `tests/test_file_size.py`، CLAUDE.md.

## التصدير والمهامّ الخلفيّة
- **كلُّ تصديرٍ عبر `core.exports.services.respond_export(request, kind_name, params=None)`**، والنوعُ يُسجَّل بـ`core.exports.registry.register(kind, build=…, capability="app.action", mode="job")`؛ والبنّاءُ نقيٌّ بلا request: `build(school, user, params) → ExportResult(content, content_type, filename, rows, full_national_id, object_id)`. الوضعُ الافتراضيّ `job` (مهمّةُ `core.export.run_job`)؛ و`direct` يُرفض تسجيلُه بلا `p95_ms` و`measured_on`، وفوق سقف `DIRECT_P95_CEILING_MS`. والقدرةُ تُفحص عند الطلب وثانيةً في العامل. المصدر: `core/exports/registry.py`، ADR-0007.
- **لا `render_pdf` ولا `Workbook` جديدٌ داخل دالّة عرض**، ولا `log_export(kind)` بلا بنّاءٍ مسجَّل — `tests/test_export_guards.py` (`SYNC_ONLY_KINDS` و`HEAVY_IN_VIEWS` تنقص ولا تزيد؛ من حوّل نوعاً حذف بندَه في الطلب نفسه).
- **لا `apply_async(queue="…")` باسمٍ حرفيّ:** خادمُ الجلسة والمعاينة طابورُهما `SESSION_NAMESPACE` (اسمُ القاعدة)، وعاملُهما لا يسمع «celery» فيبقى العملُ معلَّقاً. المصدر: `tests/test_export_core.py`، `shschool/settings/development.py`.
- العاملُ لا يعيد تحميل الكود: بعد تعديل مهمّةٍ أعِد تشغيلَه (CLAUDE.md، «خادم الجلسة»). وإعادةُ تشغيل العامل وbeat بعد نشرٍ يمسّ المهامّ شأنُ جلسة النشر.
- رموزُ خطأ التصدير ثابتة (`timeout|too_large|failed|forbidden`) — لا `str(exc)` للعميل ولا `exc_info` في السجلّ.

## البيانات الشخصيّة والتدقيق (تفصيلُها في مهارة pdppl-pii-audit)
- حقلٌ حسّاس = `core.fields.EncryptedTextField` (Fernet، يفكّ عند القراءة). أمثلة: `HealthRecord` (الحساسية، الأمراض المزمنة، الأدوية، جهة الطوارئ — لا فصيلة الدم)، و`ClinicVisit` (السبب، الأعراض، الإجراء)، ونصوصُ المخالفة الحسّاسة.
- الرقمُ الشخصيّ: نصٌّ + `national_id_encrypted` + `national_id_hmac` (البحثُ بالبصمة)؛ لا تعرضه ولا تسجّله.
- **`AuditLog` غيرُ قابلٍ للحذف ولا للتعديل الجماعيّ** (م.19) إلّا فصلَ هويّة الفاعل `user=None` عند المحو.
- **المحوُ (م.18):** `governance/erasure_service.py` يُجهّل بيانات الطالب في كلّ النماذج ويبقي الإحصاء؛ والاحتفاظُ `governance/retention.py` ووثيقتُه `docs/privacy/data_retention.md`. جدولٌ جديدٌ فيه بياناتٌ شخصيّة يدخل قائمتيهما (قوائمُ صريحةٌ بحرّاس، لا تسجيلٌ ذاتيّ — ADR-0004 §2).
- `SoftDeleteModel` معرَّفٌ في `core/models/base.py` **ولا يرثه نموذجٌ اليوم**؛ فلا تفترض «حذفاً ناعماً للطلاب». الموظّفُ المغادر `Membership.left_at`، والطالبُ المنقول `StudentTransfer`، والمحوُ بالتجهيل.

## قواعدٌ عامّةٌ للكتابة
- **لا تاريخَ حرفيّاً في المنطق** — الموضعُ الوحيد `core/management/commands/seed_academic_calendar.py` (`tests/test_no_literal_dates_in_logic.py`). العامُ من `academic_year_for(request)` أو `academic_year_for_school(school)`، والتصفيةُ بالعام بـ`YearScopedQuerySet.of_year()/live()` حيث وُجدت.
- **الهجراتُ توسيعٌ ثمّ تقليص**؛ الحذفُ والإعادةُ والـNOT NULL بلا افتراضٍ على إصدارين (CLAUDE.md، بوّابةُ `migration-linter`)؛ الفحصُ بمهارة schoolos-migration-guard. وهجراتُ `roadmap/` لجلسة الخارطة وحدَها.
- **التعليقاتُ وسلاسلُ التوثيق بالعربيّة والمعرّفاتُ بالإنجليزيّة**، وحوِّل ما تلمسه فقط (ذاكرة `feedback_code_comments_arabic.md`).
- **الاختباراتُ** تُشغَّل من شجرتك بإعدادات `testing` — الأمرُ في CLAUDE.md («سير العمل» البند 3)؛ وخطواتُ الخادم والمنفذ في مهارة schoolos-flow.
- الألوانُ في Python من `core/brand.py` لا hex حرفيّ؛ والـCSS وملفّاتُه الثمانية ورموزُ التباعد عند web-design-mastery وCLAUDE.md.

## أنماطٌ مضادّة
- منطقٌ عميقٌ أو حلقةُ ORM في view «لأنّها صغيرة الآن».
- `from assessments…` داخل `core/` لإضافة ميزة لوحة.
- `HttpResponse(render_pdf(...))` في عرضٍ جديد، أو `Workbook()` مباشرةً.
- حقلُ ملاحظاتٍ صحّيّةٍ أو سلوكيّةٍ `TextField` عاديّ.
- `date(2026, 9, 1)` في شرط.
- `queue="celery"` أو `queue="default"` في `apply_async`.
