# أنماطُ المشروع: العلاقاتُ الحقيقيّة وما يستعلم خفيةً

متى تقرأ هذا الملف: قبل أن تكتب `select_related`/`prefetch_related` لنموذجٍ في SchoolOS، أو حين لا يظهر N+1 في الشيفرة ويظهر في العدّ.

## العلاقاتُ الأكثرُ مروراً (main، 2026-09-28)
| النموذج | العلاقة | النوع | ملاحظة |
|---|---|---|---|
| `StudentEnrollment` (`core/models/academic.py`) | `student` ← `CustomUser` | FK، `related_name="enrollments"` | لا حقلَ `school`: المدرسةُ `class_group__school` |
| `StudentEnrollment` | `class_group` ← `ClassGroup` | FK، `related_name="enrollments"` | `is_active` على التسجيل |
| `ClassGroup` | `school`، `time_band`، `wing`، `supervisor` | FK | لا حقلَ `name`: `short_label`/`label_with_track`/`short_code` خصائصُ من حقولها (`grade`، `section`، `track`) بلا استعلام |
| `Subject` (`operations/models/schedule.py`) | `school` (`related_name="subjects"`) | FK | `Meta.ordering = ["name_ar"]` |
| `Session`، `StudentAttendance` (`operations`) | انظر `api/views.py`: `select_related("class_group", "subject", "teacher")` و`("student", "session__subject", "session__class_group")` | FK | |
| `CustomUser` | `memberships` ← `Membership` (المدرسة والدور) | عكسيّ | الدورُ والمدرسةُ ليسا حقلين على المستخدم |

المفتاحُ الأساسيّ غالباً UUID، فعدُّ `str(obj.pk)` في الاختبارات مقصود.

## ما يستعلم وهو لا يبدو استعلاماً
- **`user.role`، `user.get_role()`، `user.school`، `user.get_school()`، `user.active_membership`:** كلُّها تمرّ بـ`active_memberships` — استعلامٌ واحدٌ **لكلّ كائن مستخدم** يُحفظ على الكائن (`core/models/user.py`). في صفحةٍ واحدةٍ لمستخدمٍ واحد لا بأس؛ في قائمة مئة مستخدمٍ مئةُ استعلام، و`prefetch_related("memberships")` لا يُنقذها لأنّ الخاصيّة تستدعي `.filter()` على المدير.
- **`user.has_role("x")`:** استعلامُ `exists()` في كلّ نداء — لا حفظ.
- **`get_<field>_display`:** لا يستعلم (من `choices`).
- **`__str__` لنموذجٍ يقرأ علاقة:** `{{ route }}` في قالبٍ لـ`BusRoute` يقرأ `self.bus.bus_number` (`transport/models.py`) — استعلامٌ لكلّ صفٍّ ما لم يُجلب `bus`.
- **المديراتُ المخصّصة:** `.live(school, year=…)` في `core/querysets.py::YearScopedQuerySet` تبني استعلاماً؛ إن نودي بها داخل حلقةٍ لكلّ صفّ فهي N+1 مهما كان مصدرُ الحلقة.

## أين يُصلَح
- **الـselectors:** دوالُّ قراءةٍ تُرجع استعلاماً محسّناً، في ملفّاتٍ باسم المجال لا باسمٍ واحد: `behavior/selectors.py`، `reports/selectors.py`، `core/dashboard_selectors.py`، `operations/schedule_selectors.py`، `academic_management/assignment_selectors.py`… — أضِف إلى القائم في مجالك قبل أن تنشئ.
- **الخدمات:** `operations/services/` حزمةٌ لا ملفّ (`schedule.py`، `attendance.py`، …).
- **الـviews:** كثيرٌ منها يبني استعلامَه بنفسه (`api/views.py` كلُّها) — الإصلاحُ هناك مقبول، والانتقالُ إلى selector حين يتكرّر الاستعلام.
- **الـserializers:** لا تستعلم؛ ما تقرؤه من علاقاتٍ يُجهَّز في `get_queryset`.

## سوابقُ صحيحةٌ تُحتذى
- `api/views.py::StudentListView.get_queryset` — `select_related("student", "class_group")`.
- `api/views.py` (سطورٌ متعدّدة) — `.select_related("setup__subject")  # تجنب N+1 عند الوصول لاسم المادة`.
- `tests/test_n_plus_one_queries.py` — سبعُ صفحاتٍ أُصلحت 2026-09-14، وكلُّ اختبارٍ سقط قبل إصلاحه بالأرقام المذكورة في تعليقه (مثلاً «كان 3 × الأبناء، صار استعلامين»).
- `tests/test_admin_changelist_queries.py` — قوائمُ لوحة الإدارة: 373 ← ثابت.
ولا `prefetch_related` في `api/views.py` حاليّاً؛ ما ادّعاه الإصدارُ السابق من المهارة غيرُ صحيح.

## أنماطٌ مضادّة
- كتابةُ `select_related("school")` على `StudentEnrollment` — لا علاقةَ بهذا الاسم؛ Django يرفضها (FieldError) عند التنفيذ لا عند الكتابة.
- `prefetch_related("memberships")` لإنقاذ `user.get_role` في قائمة.
- إصلاحُ قالبٍ بنقل المنطق إلى `templatetag` يستعلم لكلّ صفّ — نقلٌ للمشكلة لا حلّ.
- افتراضُ أنّ الخاصيّة (`@property`) مجّانيّة دون قراءة جسمها.
