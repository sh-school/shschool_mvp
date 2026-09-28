# schoolos-platform — سجلُّ التجويد

التحقّقُ على `origin/main@81bc4937` (2026-09-28 20:07 الدوحة) بـ`git ls-tree` و`git show` و`git grep`، وعلى ذاكرة المشروع. الأصل: ملفٌّ واحدٌ 234 سطراً. الجديد: `SKILL.md` (50 سطراً) + خمسةُ مراجع + `99-test-cases.md` (420 سطراً إجمالاً دون هذا الملفّ؛ أطولُ مرجعٍ 77 سطراً).

## 1) سجلُّ الادّعاءات

| # | ادّعاءُ الأصل | الحكم | الدليل |
|---|---|---|---|
| 1 | الحزمة Django 5 + PostgreSQL + HTMX | صحيح بلا إصدار | `requirements.txt` Django 5.2.17؛ `static/js/htmx.min.js` 1.9.12؛ PostgreSQL: انظر §3 |
| 2 | `core/models/user.py` → CustomUser | صحيح | `core/models/user.py:25` |
| 3 | `academic.py` → AcademicYear, ClassGroup, StudentEnrollment, ParentStudentLink | صحيح (ناقص Wing، Semester، TimeBand…) | `core/models/academic.py` |
| 4 | `access.py` → Role **(20 دور)**, Membership | الأسماء صحيحة؛ العددُ قديم: 36 خياراً | `Role.ROLES` (عددتُها آليّاً = 36) |
| 5 | `base.py` → TimeStampedModel, SoftDeleteModel, SchoolScopedModel | صحيح (ناقص AuditedModel) | `core/models/base.py` |
| 6 | `audit.py` → AuditLog, ConsentRecord, BreachReport, ErasureRequest | صحيح | `core/models/audit.py` |
| 7 | حزمة `operations/models/` وأصنافُها | صحيح | `operations/models/{schedule,attendance,substitution}.py` |
| 8 | نماذج `assessments/models.py` الستّة | صحيح (ناقص ExamDeprivation، ExamMisconduct) | `assessments/models.py` |
| 9 | ViolationCategory **40 مخالفة — لائحة المدرسة** | قديم: الدليل 2026 = 41 (9/7/10/15) | `behavior/conduct_2026.py` (41 رمزاً فريداً) |
| 10 | `quality/models.py` → Operational… | الأسماءُ صحيحة؛ المسارُ قديم: حزمة `quality/models/` | `git ls-tree origin/main quality/models/` |
| 11 | notifications/clinic/library/exam_control/transport | صحيح | ملفّاتُ النماذج |
| 12 | HealthRecord «مشفّر Fernet» | صحيحٌ جزئيّاً: الحقولُ الحسّاسة لا كلُّها (فصيلةُ الدم نصّ) | `clinic/models.py:40-55` |
| 13 | `reports/services.py` يولّد Excel + PDF | جزئيّ: الـPDF من `core/pdf_utils.py`، والتصديرُ الجديد عبر `core/exports` | ADR-0007 |
| 14 | analytics/services KPI؛ notifications services/hub | صحيح | `AnalyticsService`، `KPIService`، `NotificationService`، `NotificationHub` |
| 15 | لا Student ولا Teacher model | صحيح | `git grep "^class (Student|Teacher)\("` بلا نتيجة |
| 16 | مثالُ استعلام الطلاب بـ`memberships__…` | يعمل، لكنّ الأدقّ `in_school`/`StudentEnrollment` | `core/querysets.py:124-160` |
| 17 | `user.role` اسمُ الدور، `has_role` bool | صحيح مع دقّة: `role` هو الدورُ **الحاكم** (الكادرُ يتقدّم) | `core/models/user.py:206-290` |
| 18 | «المستهدف» 15/5/20 + 15/5/40 | صحيح، **وهو المنفَّذ الآن** (من القرار 14/2018) | `core/domain/grades.py` `PACKAGE_MARKS_STANDARD` |
| 19 | «ما في الكود حالياً» P1 50%/P4 50%… | قديم — لم يعد في الشيفرة | `AssessmentPackage.DEFAULT_WEIGHTS_S1/S2` |
| 20 | حدُّ النجاح «المطلوب 60%» والتزم به | **خاطئٌ خطِر**: `PASS_MARK = 50` بنصّ السياسة، ولا مصدرَ لـ60 | `core/domain/grades.py:447`؛ لا أثرَ لـ60 في `AAdocs/ministry_data` ولا الذاكرة سوى ملخّص المهارة القديم |
| 21 | أنواعُ Assessment سبعة | قديم: تسعة (+classwork، makeup) | `Assessment.ASSESSMENT_TYPE` |
| 22 | حالاتُ AnnualSubjectResult أربع | قديم: عشر | `RESULT_STATUS_CHOICES` |
| 23 | قائمةُ الأدوار 20 × 5 | قديم (T3 أربعة، T4 خمسةٌ وعشرون، و`specialist`) | `TIER_*` في `access.py` |
| 24 | `is_leadership` T1+T2، `is_teacher` | صحيح | `user.py:339-348` |
| 25 | «معظمُ النماذج ترث SchoolScopedModel» | **خاطئ**: أربعةٌ فقط | `git grep "(SchoolScopedModel)"` |
| 26 | SchoolPermissionMiddleware + RLSMiddleware | صحيح (والهويّةُ منذ 0037 من دور الاتصال) | `core/middleware_rls.py` |
| 27 | `school=request.user.school` في كلّ query | قديم: `request.school`، والسقّاطةُ تعدّ `get_school()` | `SchoolContextMiddleware`؛ `regression_guards.md` |
| 28 | رموز «1-01"…"4-13» | قديم: حتّى 4-15 | `conduct_2026.py` |
| 29 | `tags` فارغة «لم يطلبها المدير» | الحقلُ موجود؛ «لم يطلبها» لا يمكن التحقّق | لا مصدر؛ حُذفت العبارة |
| 30 | حقولُ BehaviorInfraction للدرجتين 3 و4 | صحيح | `behavior/models.py` |
| 31 | الحضور: Session، StudentAttendance، AbsenceAlert | صحيح؛ و`excuse_type` قديم (خمسةٌ مغلقة + other) | `attendance.py`، `absence_policy.py` |
| 32 | الإشعارات خمسُ قنوات وتفضيلاتٌ وأولويّات وTwilio مشفّر | صحيح | `channels.py`، `hub.py`، `admin.py` |
| 33 | دوالّ ReportDataService الأربع | صحيح | `reports/services.py:49-255` |
| 34 | ExcelService: الألوان، RTL، تجميد، مرشّح، حماية، A4، أحمر<50، «أخضر للنجاح» | صحيح؛ الأخضرُ لنسبة الحضور، وA3 أفقيّ أيضاً | `reports/services.py:999-1350`، `core/brand.py` |
| 35 | شجرةُ القرار: services/api/templates/tasks | صحيح | البنية |
| 36 | «المعلّم: SubjectClassSetup.teacher أو **TeacherAssignment**» | **خاطئ**: لا `TeacherAssignment`؛ الإسنادُ `SubjectClassAssignment` والنطاقُ `get_teacher_student_ids` | `git grep TeacherAssignment` بلا نتيجة |
| 37 | «AssessmentPackage.weight يحدّد وزن كلّ باقة» | **خاطئ** للحساب: الوزنُ من القرار، والمخزَّنُ للعرض | `exact_package_weight` (تصحيح 2026-09-16) |
| 38 | national_id مشفّر والبحثُ HMAC | صحيح، مع بقاء النصّ `USERNAME_FIELD` | `user.py:27-140` |
| 39 | 2FA TOTP مشفّر | صحيح (يُشفَّر عند التفعيل) | `core/views_auth.py:410` |
| 40 | **Soft Delete: لا حذف فعلي لبيانات الطلاب** | **خاطئ**: لا نموذجَ يرث SoftDeleteModel؛ المحوُ تجهيلٌ في `governance/erasure_service.py` | `git grep "SoftDeleteModel)"` |
| 41 | CSP middleware، AuditLog + PermissionAuditLog | صحيح (django-csp 4 يقرأ `CONTENT_SECURITY_POLICY` وحده) | `settings/base.py:423` |
| 42 | الوصف «تلقائياً عند أيّ عمل» | فضفاض: يتداخل مع الفلو والتصميم والهجرات | الكرّاسة §2 |

## 2) التغييرات

| البند | القديم | الجديد | السبب | الدليل |
|---|---|---|---|---|
| البنية | SKILL.md واحد 234 سطراً | SKILL.md 50 سطراً + 00..04 + 99 | الكرّاسة: ≤120 ومراجعُ بسطر «متى تقرأ» | BRIEF §2 |
| الوصف | عربيٌّ واحدٌ «عند أيّ عمل» | إنجليزيٌّ ثمّ عربيّ، عباراتُ تفعيلٍ عاميّة، وقسم «Not for» بأسماء المهارات | منعُ التفعيل الخاطئ | BRIEF §2 |
| التقييم | «الكود يختلف عن المالك؛ التزم بـ60» | المنفَّذُ هو القرار 14/2018، `PASS_MARK=50`، الصفُّ 12، الجبرُ، الحالاتُ العشر، محرّكُ الحكم ورايتُه | الأصلُ يدفع لكسر حكمٍ صحيح | `core/domain/grades.py`، `verdict_engine.py` |
| الأدوار | 20 × 5 | 36 خياراً بجدول المستويات + المجموعاتُ المشتقّة + الوراثة | تغيّرت منذ v7 و2026-09-06 | `access.py`، `permissions.py` |
| المدرسة | `request.user.school`، «معظمُها SchoolScopedModel» | `request.school`، تصنيفُ `core/tenancy.py`، RLS بدور الاتصال، PgBouncer | خاطئ/قديم | الملفّات المذكورة |
| الفخاخ | ثلاثٌ عامّة | ثمانٍ خطأ:/الصواب: في SKILL.md وأنماطٌ مضادّةٌ في كلّ مرجع | الكرّاسة | — |
| جديد | — | خريطةُ URL→تطبيق (`teacher/`، `academic/`، `import/`)، جداولُ `core_*` الموروثة، الأسماءُ المكرّرة | فخاخُ بحثٍ حقيقيّة | `shschool/urls.py`، `Meta.db_table` |
| جديد | — | القيدان النشطان و`current_of`؛ `TEACHING_ROLES`؛ `has_parent_membership`؛ `grade_number` | أخطاءٌ مقيسةٌ في تعليقات الشيفرة | `academic.py`، `access.py`، `user.py` |
| جديد | — | عتباتُ الغياب ودلالةُ «تجاوز» وقراراتُ المدرسة | لا وجودَ لها في الأصل | `absence_policy.py` |
| جديد | — | دليلُ السلوك 2026، العدّاد، هجرةُ الأسماء | — | `conduct_2026.py`، ذاكرة `project_conduct_catalog_db_names_need_migration.md` |
| جديد | — | الإشعار: `NotificationHub` وحدَه، الموافقةُ الصريحة، رايةُ المسار المتتبَّع | — | `hub.py` |
| جديد | — | الطبقات (60 سطراً/5 ORM، core لا يستورد نازلاً)، التصدير المركزيّ، الطابور الحرفيّ، حجمُ الملفّ، التواريخ الحرفيّة، التشفير، المحو | حرّاسٌ تُسقط البناء | `docs/architecture/layering.md`، ADR-0004/0007، الاختبارات المسمّاة |
| حُذف | «الأوزان المطلوبة ليست ما في الكود» و«حد النجاح المطلوب 60» و`TeacherAssignment` وSoft Delete | — | قديمٌ أو خاطئ | §1 |

## 3) يحتاج قرارَ المالك أو تأكيدَه
1. **حدُّ النجاح:** المهارةُ القديمة قالت «المالك يريد 60%». الشيفرةُ والسياسةُ 50، ولم أجد لـ60 مصدراً غيرَ المهارة نفسِها وملخّصِها في الذاكرة (`skills_schoolos_platform.md`). إن كان للمالك قرارٌ بـ60 فيُسجَّل ويُراجَع مع المستشار؛ وإلّا فيُحدَّث ملخّصُ الذاكرة.
2. **الصفُّ الثاني عشر:** ذاكرة `project_grade12_ministry_exams.md` (09-19) تقول لا رصدَ ولا حكمَ له في المنصّة، والشيفرةُ فيها فرعُه كاملاً. أيّهما الساري؟
3. **إصدارُ PostgreSQL:** المحلّيُّ 18، وتعليقُ `backup.yml` يقول الإنتاجُ 18، بينما بوّاباتُ CI و`docker-compose.prod.yml` وREADME و`DEPLOYMENT-RAILWAY.md` على 16. أيُّها المرجع؟ وهل تُرفع بوّاباتُ CI؟
4. **رايتا الحكم والإشعار:** حالُ `VERDICT_ENGINE_ENABLED` في الإنتاج لا يُعرف من الشيفرة (الافتراضُ مطفأة)؛ ورايةُ مسار التسليم مطفأةٌ «في الإنتاج» بتعليق الشيفرة. للتأكيد من جلسة النشر.
5. **تعليقاتٌ متقادمةٌ في الشيفرة:** docstring `behavior/models.py` «40 مخالفة»، وتعليقُ `Membership.role` «ثمانيةٌ وعشرون دوراً» — مهمّةُ تنظيفٍ صغيرة إن رأى المالك.
6. **`CustomUser.objects.students(school)`** يسلسل `filter()` مرّتين بلا `is_active` (قراءتي للشيفرة، لا بلاغ). يُفحص إن كان مقصوداً.
7. **ذاكرةٌ متقادمة:** `skills_schoolos_platform.md` (20 دوراً، 60) و`project_behavior_pending.md` («66 فئة مخالفة») تخالفان الشيفرة؛ تُحدَّثان بعد اعتماد هذه النسخة.
