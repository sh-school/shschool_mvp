# اختبارُ النقطة وما يشغّله CI عليها

متى تقرأ هذا الملف: حين تملأ الاختبارَ المولَّد، أو يسقط اختبارُك أو حارسٌ في CI بعد إضافة النقطة.

## ما يولّده السكربت في `tests/test_<name>_api.py`
| الاختبار | يثبت | ملاحظة |
|---|---|---|
| `test_anonymous_gets_401` | من لا جلسةَ له يُردّ | الوسيطُ يردّ 401 قبل حلّ المسار — فهو يمرّ حتّى لو لم تُسجَّل النقطة؛ لا يثبت وجودَها وحده |
| `test_role_without_permission_gets_403` | الدورُ الخطأ يُردّ | 404 هنا يعني أنّ المسار غيرُ مسجَّل |
| `test_other_school_rows_are_invisible` | عزلُ المدارس | صفٌّ في مدرستك وآخر في `SchoolFactory()` |
| `test_query_count_does_not_grow_with_rows` | لا N+1 | إحماء، ثمّ صفٌّ مقابل ثلاثة؛ يطبع SQL عند السقوط |
| `test_create_is_idempotent` (للإنشاء) | الإرسالُ المكرّر يعيد الصفَّ نفسَه | 201 مرّتين والمعرّفُ واحد |
| `test_school_cannot_be_injected` (للإنشاء) | `school` في الحمولة لا أثرَ لها | لا صفَّ في المدرسة الأخرى |

`make_row(school)` و`payload()` ترفعان `NotImplementedError` حتّى تكتبهما — الاختبارُ يسقط عمداً بدل أن يمرّ فارغاً. الأفضلُ مصنعٌ في `tests/conftest.py` إن كان النموذجُ سيُختبر كثيراً (`SchoolBusFactory`، `LibraryBookFactory`… قائمة).

## fixtures الأدوار (`tests/conftest.py`)
`school`، `principal_user`، `teacher_user`، `student_user`، `parent_user` (موافقٌ ومربوطٌ بـ`student_user`)، `nurse_user`، `librarian_user`، `bus_supervisor_user`، `specialist_user` وغيرُها — كلٌّ بعضويّةٍ في `school`. وتُرى فقط للاختبارات تحت `tests/`.
اختيارُ السكربت الافتراضيّ للمسموح والممنوع: `IsTeacherOrAdmin` ← teacher/student؛ `IsSchoolAdmin` و`IsLeadership` ← principal/teacher؛ `IsStaffMember` ← teacher/student؛ `IsParentOrAdmin` ← parent/teacher. غيّره إن كان دورُك غير ذلك.

## الدخول
`Client().force_login(user)` (جلسة Django). `APIClient.force_authenticate` يضع المستخدمَ في طلب DRF فقط، والوسيطُ قبله يرى مجهولاً فيردّ 401. مُثبَتٌ في مختبرٍ على نسخةٍ من main: اختبارُ الإصدار القديم من المهارة أخذ 401 حيث توقّع 403 و200 و201.
ولا تحتاج CSRF في الاختبار: عميلُ اختبار Django يعلّم طلباته بإعفاء CSRF، وDRF يحترمه.

## التشغيل
داخل حاوية جلستك بأمر الاختبار في `CLAUDE.md` (إعدادات `testing`، وقاعدةُ اختبارٍ باسم جلستك):
```
tests/test_<name>_api.py tests/test_every_route_is_guarded.py tests/test_api_contract.py tests/test_file_size.py
```
- `test_every_route_is_guarded`: صلاحيّتُك دورٌ لا «مسجَّل الدخول».
- `test_api_contract`: المخطّطُ يُولَّد (`/api/v1/schema/`) — `@extend_schema` بعنوانٍ عربيٍّ ووسم.
- `test_file_size`: لم يكبر ملفٌّ مسجَّل ولم يتجاوز جديدٌ 1000.
- ruff بإصدار CI (0.4.4) لا بإصدار الحاوية: `ruff check <ملفّاتك>` و`ruff format --check <ملفّاتك>` — طريقةُ تثبيته المعزولة في ذاكرة `feedback_ci_gates_that_bit_2026_09_23.md` (البند 6).
- `makemigrations --check` إن أضفتَ قيداً أو حقلاً (مهارة schoolos-migration-guard).

## ما جُرّب
مختبرٌ خارج المستودع (نسخةٌ من main@81bc4937، PostgreSQL 18، صورة الحاوية)، 2026-09-28:
- توليدُ `bus-routes` (قراءة، `--school-path bus__school`) و`lab-subjects` (إنشاءٌ على `Subject` بمفتاح `code`) ثمّ توزيعُهما في `api/views_*.py` و`api/urls.py` وكتابةُ `make_row`/`payload`: 10 اختباراتٍ خضراء، وحارسُ المسارات أخضر.
- قبل كتابة `make_row`: تسقط اختباراتُ العزل والثبات بـ`NotImplementedError`، ويسقط 403 بـ404 إن لم يُسجَّل المسار.
- الإصدارُ القديم: ملفُّه في `operations/tests/` ← 5 أخطاءٍ «fixture not found»؛ ولمّا نُقل إلى `tests/` ← 401 في كلّ طلبٍ مصادَق.

## أنماطٌ مضادّة
- حذفُ `test_role_without_permission_gets_403` لأنّه «يطلع 404» — المسارُ غيرُ مسجَّل، أصلِحه.
- رفعُ عدد الاستعلامات المسموح حتّى يخضرّ اختبارُ الثبات.
- `make_row` تُنشئ صفَّ المدرسة الأخرى في مدرسة المستخدم نفسِها — العزلُ يمرّ كاذباً.
- تشغيلُ الاختبارات على المضيف: `conftest.py` في الجذر يوقف التشغيلَ إن لم يكن Celery فوريّاً، والإعداداتُ الصحيحة في الحاوية.
