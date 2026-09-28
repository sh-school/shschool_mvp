# 01 — المستخدمون والأدوار وعزلُ المدرسة

> متى تقرأ هذا الملف: حين تستعلم عن طلبةٍ أو معلّمين أو أولياء أمور، أو تكتب حارسَ صلاحيّة، أو تضيف جدولاً يحمل بياناتِ مدرسة، أو تعالج بلاغَ دخول.

## المستخدمُ الموحَّد
- `core.models.CustomUser` (مفتاحُه UUID) لكلّ الناس. لا نموذجَ للطالب ولا للمعلّم.
- الدورُ ليس حقلاً فيه: `Membership(user, school, role→Role, is_active, joined_at, left_at, department_obj, job_title)`. المصدر: `core/models/access.py`.
- **العضويّةُ مدّة:** المغادرةُ تُكتب `left_at` وسببَها ومرجعَ قرارها، و`is_active` يُطفأ معها. للسؤال في تاريخٍ: `Membership.objects.active_on(date)` و`current()`؛ والمنصرفون `departed()`. لا حذفَ لعضويّة من غادر (جدولُ عامه الماضي يبقى منسوباً إليه).
- `ParentStudentLink(parent, student, school, relationship, can_view_grades|attendance|behavior)` يربط وليَّ الأمر بابنه. المصدر: `core/models/academic.py`.

## خصائصُ المستخدم — وما تعنيه فعلاً
المصدر: `core/models/user.py`.

| النداء | يُرجع | الفخّ |
|---|---|---|
| `user.active_membership` | العضويّةُ **الحاكمة** مرتّبةً بـ`role_rank()`: الكادرُ قبل وليّ الأمر والطالب | معلّمٌ ابنُه في المدرسة: الحاكمةُ «معلّم» |
| `user.role` / `get_role()` | اسمُ الدور الحاكم وحدَه | لا يصلح لسؤال «أله دورُ X؟» |
| `user.has_role(name)` / `has_any_role(*names)` | أيُّ عضويّةٍ نشطةٍ بهذا الدور | استعلامٌ في كلّ نداء — لا تضعه في حلقة |
| `user.has_parent_membership` | أله عضويّةُ وليّ أمر (من المحفوظ، بلا استعلام) | استعمله بدل `has_role("parent")` في القوالب |
| `user.school` / `get_school()` | مدرسةُ العضويّة الحاكمة | في العروض اقرأ `request.school` |
| `user.is_teacher()` | الحاكمُ ∈ {teacher, coordinator, ese_teacher} | يختلف عن `TEACHING_ROLES` (من يحمل نصاباً) |
| `user.is_leadership()` | superuser أو principal/vice_admin/vice_academic | |
| `user.invalidate_active_membership()` | يُبطل الذاكرةَ المحفوظة على الكائن | نادِه بعد إنشاء عضويّةٍ أو تعديلها في الطلب نفسه |

استعلاماتُ المدير (`core/querysets.py::UserQuerySet`):
- `CustomUser.objects.in_school(school)` — منتسبو المدرسة بعضويّةٍ نشطة، صفٌّ واحدٌ لكلّ إنسان (استعلامٌ داخليّ لا ضمّ؛ الضمُّ يكرّر صاحبَ العضويّتين).
- `CustomUser.objects.teachers(school)` — `TEACHING_ROLES` بعضويّةٍ نشطةٍ في المدرسة نفسها.
- `CustomUser.objects.students(school)` — يسلسل `filter()` مرّتين ولا يشترط `is_active`: قد يطابق دورَ طالبٍ في مدرسةٍ وعضويّةً أخرى في هذه. لطلبة شعبةٍ أو مدرسةٍ بدقّة اعبر `StudentEnrollment`. (ملاحظةٌ من قراءة الشيفرة، لا بلاغَ مسجَّلاً.)

## الأدوار — 36 خياراً في خمسة مستويات ونظام
المصدر: `core/models/access.py` (`Role.ROLES` والمجموعات `TIER_*`). `Role` صفٌّ **لكلّ مدرسة** (`UniqueConstraint(school, name)`): ارشّح بـ`role__name` لا بمعرّف `Role` من مدرسةٍ أخرى.

| المستوى | الأدوار |
|---|---|
| 1 قيادة | `principal` |
| 2 نوّاب | `vice_admin` `vice_academic` |
| 3 إشراف | `coordinator` `admin_supervisor` `activities_coordinator` `e_projects_coordinator` |
| 4 كادر (25) | تدريس: `teacher` `ese_teacher` `teacher_assistant` `ese_assistant` · دعم: `social_worker` `psychologist` `academic_advisor` `speech_therapist` `occupational_therapist` `support_companion` · خدمات: `nurse` `librarian` `it_technician` `bus_supervisor` `transport_officer` · إداريّون: `admin` `secretary` `receptionist` `student_observer` `lab_technician` `storekeeper` `accountant` `canteen_supervisor` `services_worker` `messenger` |
| 4 قديم | `specialist` (توافقٌ خلفيّ) |
| 5 مستفيدون | `student` `parent` |
| 0 نظام | `platform_developer` |

مجموعاتٌ مشتقّة تُستعمل ولا تُعاد كتابتُها: `TEACHING_ROLES` (teacher, coordinator — قرار 2026-09-02)، `EXEMPTABLE_ROLES`، `DEPARTMENT_ROLES` (من له قسمٌ أكاديميّ)، `ACADEMIC_ROLES`، `ALL_STAFF_ROLES` (ومعها `platform_developer`). و`job_title` في العضويّة هو المسمّى الوظيفيّ الحرفيّ للكشوف؛ الدورُ مفتاحُ صلاحيّات لا مسمّى.

## الصلاحيّات
- **الوراثة:** `core/permissions.py::ROLE_INHERITS` — المنسّقُ يرث المعلّم، والنائبُ الأكاديميّ يرث المنسّق، والمديرُ يرث النائبَ الأكاديميّ، والنائبُ الإداريّ يرث المشرفَ الإداريّ… و`expand_roles()` يوسّعها.
- **حارسُ المسارات:** `SchoolPermissionMiddleware` (`core/middleware.py`) يمنع بادئةَ كلّ وحدةٍ عن غير أدوارها، والبادئاتُ تسجّلها التطبيقاتُ في `ready()` بـ`core.module_registry.register_module(name, url_prefix, allowed_roles, …)` — ومنها قائمةُ الوحدات في الشريط. وحدةٌ جديدةٌ بلا تسجيلٍ لا يحرسها الوسيط.
- **الحرّاس:** `role_required(*roles)`، `permission_required(SET)`، `department_scoped`، و`staff_required`/`leadership_required`… كلُّها في `core/permissions.py`؛ والقدرةُ بالفعل لا بالدور: `core/capabilities.py::capability_required("app.action")` و`has_capability`؛ ومنحُ قدرةٍ لشخصٍ بلا تغيير دوره `CapabilityGrant` يُكتب بـ`core/capability_grants.py` وحدَه (يفحص المانحَ ويشترط السبب ويدقّق)، ويُسحب ولا يُحذف.
- **مجموعةٌ جديدة** تُكتب في `core/permissions.py` لا في `views*.py` — وإلّا سقط `tests/test_permission_groups_are_central.py`.
- **من يرى أيَّ طالب:** `get_teacher_student_ids(user, scope)` — `None` = الكلّ (القيادة والأخصائيّون)، والمعلّمُ طلبةَ فصوله من `ScheduleSlot`، والمنسّقُ قسمَه. و**المشرفُ الإداريُّ لجناحه وحدَه** (قرارا 2026-09-14/15): كلُّ شاشةٍ تأخذ `wings.scope.student_scope_for(request)` وتمرّر استعلامَها على `scope.narrow(qs)`، وكلُّ معرّفٍ من الرابط على `scope.require_student(id)` (404 لما خرج). والتقييدُ بالدور **الخامّ** لا الموسَّع (النائبُ يرث المشرفَ ولا يُقيَّد). المصدر: `wings/scope.py`.

## عزلُ المدرسة (Multi-tenancy)
- **في العرض:** `request.school` (من `SchoolContextMiddleware`)، وكلُّ استعلامٍ على بياناتِ مدرسةٍ يُرشَّح بها.
- **في القاعدة:** RLS. `RLSMiddleware` يضبط `app.current_school_id` لكلّ طلب ويُغلق الطلبَ بـ503 إن تعذّر (fail-closed)؛ ومنذ هجرة `core/0037` تُشتقّ هويّةُ المستأجر في السياسات من **دور الاتصال** لا من هذا المتغيّر. المصدر: `core/middleware_rls.py`، `core/rls.py`.
- **الضبطُ بمستوى الجلسة** (`set_config(..., false)`) — لا تُضِف PgBouncer بوضع transaction pooling قبل إعادة كتابته بـ`SET LOCAL`. المصدر: ذاكرة `project_rls_pgbouncer_incompatibility.md`.
- **كلُّ جدولٍ مصنَّف** في `core/tenancy.py`: `DIRECT_SCHOOL` (له `school_id`، يُحسب آليّاً)، `PARENT_DERIVED` (مدرستُه من أبيه — لا تُضِف له `school_id` مكرّراً)، `GLOBAL_INFRASTRUCTURE`، `SPECIAL_UNRESOLVED`. جدولٌ جديدٌ بلا تصنيفٍ يُسقط `tests/test_tenant_surface_coverage.py` — والسقوطُ مقصود ليُقرَّر لا ليقع في النقطة العمياء.
- `SchoolScopedModel` (`core/models/base.py`) ترثه أربعةُ نماذجَ فقط (`CapabilityGrant` `ExportJob` `LeaveBalance` `StudentActivity`)؛ والباقي يعلن `school = ForeignKey(School)` بنفسه. كلاهما مقبول.

## الدخول والهويّة
- الكادرُ صاحبُ `employee_number` يدخل **به وحدَه**؛ رقمُه الشخصيّ يُعامَل كمعرّفٍ مجهول (قرار ق-10، 2026-09-18). الطلبةُ وأولياءُ الأمور برقمهم الشخصيّ. والقفلُ بمفتاحٍ معياريٍّ واحد (معرّفُ المستخدم أو بصمةٌ غيرُ عكوسة). المصدر: `core/auth_identity.py`.
- بلاغُ «محاولات كثيرة جدّاً» غالباً قفلُ axes مؤقّت (`AXES_COOLOFF_TIME`) لا تعطيلُ حساب. المصدر: ذاكرة `project_employee_number_login_cutover.md`.
- `national_id` يبقى نصّاً لأنّه `USERNAME_FIELD`، ومعه `national_id_encrypted` (Fernet) و`national_id_hmac` للبحث، يُملآن في `save()`. الهاتفُ بـ`get_phone_decrypted()`. و`totp_secret` يُخزَّن مشفّراً عند التفعيل (`core/views_auth.py`).
- وسطاءُ الإلزام بعد الدخول: تغييرُ كلمة المرور، والتحقّقُ الثنائيّ، وجلسةُ MFA، وموافقةُ وليّ الأمر (`core/middleware.py`، `core/mfa_session.py`).

## أنماطٌ مضادّة
- `filter(memberships__school=s)` لعدّ الناس — يكرّر صاحبَ العضويّتين؛ استعمل `in_school`.
- `Role.objects.get(name="teacher")` بلا مدرسة — دورٌ لكلّ مدرسة، فيرفع «أكثر من واحد».
- تقييدُ المشرف بـ`expand_roles` أو بشاشةٍ بعينها بدل `student_scope_for`.
- جدولٌ جديدٌ ببيانات مدرسة دون سطرٍ في `core/tenancy.py` أو دون `school_id`.
- حذفُ عضويّة موظّفٍ نُقل بدل `left_at` + `departure_reason`.
