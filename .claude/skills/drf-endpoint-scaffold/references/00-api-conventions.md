# أعرافُ واجهة /api/v1/

متى تقرأ هذا الملف: قبل تصميم نقطةٍ جديدة، أو حين تسقط نقطتُك بـ401/403 غيرِ متوقَّع، أو يسقط حارسٌ في CI بعد إضافة مسار.

## البنية (main، 2026-09-28)
| الشيء | الحقيقة | المصدر |
|---|---|---|
| البادئة | `path("api/v1/", include("api.urls", namespace="api_v1"))` | `shschool/urls.py` |
| الوحدات | `api/views.py` (915 سطراً)، `api/views_erasure.py`، `api/serializers.py` (468)، `api/permissions.py`، `api/pagination.py`، `api/filters.py`، `api/urls.py` | `git ls-tree origin/main api/` |
| المخطّط | `/api/v1/schema/` و`docs/` و`redoc/` بـdrf-spectacular 0.30، عنوانُه «SchoolOS API» | `api/urls.py`، `SPECTACULAR_SETTINGS` |
| الإصدارات | Django 5.2.17، DRF 3.18.1 | `requirements.txt` |
| نقاطٌ أخرى | `/api/students/search/` في `operations/api_urls.py` — داخليّةٌ للشاشات، ليست من هذه الواجهة | `shschool/urls.py` |

## المصادقة
- `DEFAULT_AUTHENTICATION_CLASSES` = `SessionAuthentication` وحدها؛ وJWT يُضاف فقط إن كان `API_JWT_ENABLED` (افتراضُه False) (`shschool/settings/base.py`). فالعميلُ اليوم متصفّحٌ بجلسة.
- الوسائطُ قبل DRF (`core/middleware.py`):
  - `SchoolPermissionMiddleware`: من لا جلسةَ له على `/api/` ← 401 JSON `not_authenticated` قبل أن تُنادى الصلاحيّة. لذا `force_authenticate` لا يكفي في الاختبار.
  - `ForcePasswordChangeMiddleware` و`TwoFactorEnforcementMiddleware`: يردّان `/api/` بـJSON حين يلزم تغييرُ كلمة المرور أو التحقّقُ الثنائيّ (الأخيرُ مطفأٌ في الاختبارات: `TWO_FACTOR_REQUIRED_FOR_STAFF = False`).
  - `ParentConsentMiddleware`: وليُّ الأمر بلا موافقةٍ يُردّ في `/api/` أيضاً؛ و`IsParentOrAdmin` يعيد الفحصَ دفاعاً في العمق.

## الصلاحيّات (`api/permissions.py`)
| الصنف | من يمرّ |
|---|---|
| `IsSchoolAdmin` | `is_admin()` أو superuser |
| `IsLeadership` | superuser أو دورٌ في `LEADERSHIP` |
| `IsTeacherOrAdmin` | `is_admin()` أو دورٌ يرث المعلّم (`expand_roles({"teacher"})`) — النائبُ الإداريّ لا |
| `IsStaffMember` | الكادرُ كلُّه و`specialist` |
| `IsParentOrAdmin` | وليُّ أمرٍ موافقٌ يملك `ParentStudentLink` لـ`student_id` في المسار، أو المدير |
| `IsSameDepartment` | القيادة، أو من قسمُه قسمُ الـview؛ بلا قسمٍ يُردّ |
كلُّها تفحص `is_authenticated` بنفسها، فـ`permission_classes = [IsTeacherOrAdmin]` وحدها صحيحة (وهو أسلوبُ `api/views.py`)، وإضافةُ `IsAuthenticated` قبلها لا تضرّ.
الحارس: `tests/test_every_route_is_guarded.py` يمشي كلَّ مسار ويطلب صلاحيّةَ DRF ليست `IsAuthenticated`/`AllowAny`، أو استثناءً مسمّى بسببه في `GUARDED_INSIDE`/`OPEN_BY_DESIGN`. الاستثناءُ يُقرأ في المراجعة — لا تضفه لتمرّ.

## الترقيم والفلترة والتحديد
- الافتراضُ `PageNumberPagination` بـ50؛ و`StandardPagination` (`api/pagination.py`) يضيف `?page_size=` بحدٍّ أقصى 200 — استعمله صراحةً كما تفعل نقاطُ القوائم القائمة. الاستجابة: `count`، `next`، `previous`، `results`.
- `DEFAULT_FILTER_BACKENDS`: `DjangoFilterBackend` و`SearchFilter` و`OrderingFilter`؛ وفلاترُ المجالات في `api/filters.py`.
- التحديد: `anon` 30/د، `user` 120/د، ونطاقاتُ `login`/`burst`/`sensitive` للنقاط الحسّاسة.

## المدرسةُ والعام
- `_school(request)` في `api/views.py` = `request.user.get_school()` (مدرسةُ العضويّة الحاكمة). و`_year(request)` = `?year=` أو العامُ الجاري من تقويم الوزارة (`core.academic_calendar.academic_year_for`).
- مسارُ المدرسة يختلف بالنموذج: `Subject.school`، `StudentEnrollment.class_group__school`، `BusRoute.bus__school`. أربعةُ نماذج فقط ترث `SchoolScopedModel` (`CapabilityGrant`، `ExportJob`، `LeaveBalance`، `StudentActivity`).

## سقوفٌ تمسّ النقطة الجديدة
- `tests/test_file_size.py`: لا ملفَّ `.py` جديدٌ فوق 1000 سطر، ولا مسجَّلٌ يكبر أكثر من 25. `api/views.py` عند 915 — الوحدةُ الجديدة أسلم.
- `ruff==0.4.4` في CI (`ruff check .` و`ruff format --check .`) — إصدارٌ غيرُ إصدار الحاوية؛ انظر `references/02-testing.md`.
- سقّاطةُ mypy (`tests/mypy_ratchet.py`) تفحص `core` و`shschool` و`governance` فقط — `api/` خارجها اليوم، فلا تعتمد عليها لكشف أخطاء أنواع النقطة.
- `.gitignore` يتجاهل `_*.py`: ملفُّ التجهيز لا يُودَع؛ ولا تسمِّ وحدةً حقيقيّةً بشرطةٍ سفليّة (ذاكرة `feedback_gitignore_underscore_modules.md`).

## أنماطٌ مضادّة
- إضافةُ نقطةٍ إلى `operations/api_urls.py` لأنّ «المسار أقصر».
- `permission_classes = [IsAuthenticated]` مع فحصٍ للدور داخل `get_queryset` دون تسميته في `GUARDED_INSIDE`.
- الاعتمادُ على JWT في تصميم نقطةٍ جديدة — مطفأٌ افتراضاً.
- `request.user.school_id` أو `request.GET["school"]` بدل `_school(request)`.
