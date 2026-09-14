# سياسةُ الاحتفاظ بالبيانات — SchoolOS

> المرجعُ القانونيّ: قانونُ حماية خصوصيّة البيانات الشخصيّة القطريّ رقم (13) لسنة 2016،
> المادّتان 7 (لا تُحفظ البياناتُ أطولَ ممّا يقتضيه غرضُها) و10 (التزاماتُ المتحكّم في
> التنظيم والحماية). والمُنفِّذ: `core/retention.py`، والحارس: `tests/test_data_retention.py`.
> أُقرّت 2026-09-14 (سواط — الموجة الثانية، البند A).

## 1. المبدأ

البياناتُ في المنصّة صنفان لا يُخلط بينهما:

1. **سجلّاتٌ يُلزم القانونُ أو الوزارةُ بحفظها** — السجلُّ الأكاديميّ والحضورُ والسلوكُ
   والصحّةُ للطلبة، وملفّاتُ الموظّفين، وسجلُّ التدقيق كلُّه. هذه **لا تُحذف بمرور الزمن**؛
   وما يخرج منها يخرج بطلب محوٍ فرديّ (`ErasureRequest`، م.18) أو بقرارٍ وزاريٍّ مكتوب.
2. **آثارُ تشغيلٍ حملت بياناتٍ شخصيّةً وانقضى غرضُها** — عنوانُ IP في محاولة دخول، بريدٌ
   ونصُّ رسالةٍ في سجلّ تسليم، إشعارُ جرسٍ قُرئ. هذه **تُحذف بعد مدّة**، لأنّ بقاءَها
   لا يخدم صاحبَها ولا المدرسةَ ويُثقل ما قد يُسرَّب.

والحدُّ بين الصنفين ليس «هل فيه بياناتٌ شخصيّة» — فكلاهما فيه — بل **هل بقي له غرض**.

## 2. المدّة والجدولة

| البند | القيمة |
|---|---|
| المتغيّر | `PDPPL_DATA_RETENTION_DAYS` (البيئة → `settings.PDPPL_DATA_RETENTION_DAYS`) |
| الافتراض | `730` يوماً (عامان دراسيّان) — في `.env.example` و`.env.railway.example` |
| التعطيل | `0` — لا يُحذف شيء، ولا يُكتب سطرٌ في التدقيق |
| أين يُقرأ | العامل (`celery-worker`) — لذا الاسمُ في `WORKER_VARIABLES` في `.railway/railway.ts` |
| المهمّة | `core.enforce_data_retention` (`core/tasks.py`) |
| الجدولة | أسبوعيّاً، الجمعة 03:30 بتوقيت قطر (`shschool/celery.py: beat_schedule`) |
| يدويّاً | `python manage.py enforce_retention` (عرض) / `--apply` (حذف) |
| الأثر | سطرٌ في `AuditLog(action="delete", model_name="other")` بالأعداد لكلّ صنفٍ — لا أسماء |
| الدفعات | ألفُ صفٍّ في جملة الحذف الواحدة (`BATCH_SIZE`) |
| التكرار | ثابتةُ التكرار: تشغيلٌ ثانٍ على قاعدةٍ نُفِّذت عليها لا يحذف شيئاً |

**النسخُ الاحتياطيّة** (Cloudflare R2): دورةُ حياةٍ 400 يوماً وقفلُ 30 يوماً، مضبوطان في
Cloudflare لا في المستودع. فما يُحذف من القاعدة يزول من آخر نسخةٍ تحمله بعد 400 يوماً على
الأكثر — وهذا سقفُ الاحتفاظ الفعليّ لا `N` وحدَه.

## 3. ما يُحذف

### 3.1 ينتهي بذاته — يُحذف عند انقضائه لا بعد N

| الجدول | الشرط | لماذا |
|---|---|---|
| `django_session` | `expire_date < now` | جلسةٌ منتهيةٌ لا تفتح شيئاً، ومحتواها الموقَّع يحمل معرّفَ المستخدم. وهو ما يفعله `clearsessions` لو أُجري. |
| `token_blacklist_outstandingtoken` | `expires_at < now` | رمزُ تحديثٍ منقضٍ لا يُقبل أصلاً. |
| `token_blacklist_blacklistedtoken` | يتبع رمزَه بالتسلسل | قائمةُ حظرٍ لرمزٍ لم يعد له وجود. |

### 3.2 يُحذف بعد N يوماً

| الجدول | الشرط | لماذا |
|---|---|---|
| `axes_accessattempt` | `attempt_time < cutoff` | عدّادُ القفل — لا معنى له بعد ساعة التهدئة، ويحمل IP ووكيلَ المستخدم ومفتاحَ المعرّف. |
| `axes_accesslog` | `attempt_time < cutoff` | تاريخُ الدخول والخروج بالـIP. الأثرُ الدائمُ في `core_auditlog` (`login`/`logout`). |
| `axes_accessfailurelog` | `attempt_time < cutoff` | كسابقه للفشل. الأثرُ الدائمُ `login_failed` في `core_auditlog`. |
| `notifications_notificationlog` | `sent_at < cutoff` | محاولةُ تسليمٍ بالبريد أو الرقم **ونصِّ الرسالة** — أثقلُ ما في الجدول. |
| `notifications_deadlettermessage` | `resolved` و`created_at < cutoff` | المحلولةُ وحدَها؛ غيرُ المحلولة طابورُ مشغّلٍ يبقى ويُعدّ (انظر §5). |
| `notifications_notificationenqueueintent` | `created_at < cutoff` ولا تسليمَ مفتوحاً لمستلمها | صندوقٌ صادرٌ مؤقّت: العنوانُ والنصُّ يُمسحان أصلاً حين تنتهي التسليمات، والصفُّ يُحذف بعد المدّة. |
| `notifications_notificationdelivery` | `created_at < cutoff` وحالةٌ نهائيّة ولا سجلَّ ولا رسالةَ فاشلةً تحميه | يُحذف بعد أبنائه (`PROTECT`)؛ فما بقي له سجلٌّ أحدثُ من المدّة يبقى معه. |
| `notifications_notificationdispatch` | `created_at < cutoff` ولا تسليمَ ولا نيّة | الواقعةُ التي لم يبقَ منها شيء. |
| `notifications_inappnotification` | `created_at < cutoff` | إشعارُ الجرس — يذكر طالباً أو مخالفةً، ولا وظيفةَ له بعد عامين قُرئ أو لم يُقرأ. |
| `notifications_pushsubscription` | `is_active = false` وآخرُ استعمالٍ (أو الإنشاءُ) `< cutoff` | اشتراكٌ مطفأ: نقطةُ نهايةٍ ومفاتيحُ متصفّحٍ لم يعد أحدٌ يستقبل بها. |
| `staging_importlog` | `started_at < cutoff` | `error_log` يحمل الصفوفَ المرفوضةَ كما وردت في الإكسل — أسماءً وأرقاماً. |

**ترتيبُ التنفيذ** جزءٌ من الصواب: سجلّاتُ التسليم والرسائلُ الفاشلة قبل التسليمات، والتسليماتُ
والنوايا قبل الوقائع — لأنّ الأوّلين يحميان الثاني (`PROTECT`) والثاني يتبع الثالثَ (`CASCADE`).
فلا يُحذف أبٌ إلّا بعد أن يخلو من أبنائه، ولا يُنسب حذفُ ابنٍ إلى قاعدة أبيه.

**ملفّاتُ التصدير المؤقّتة**: لا وجودَ لها. التصديرُ (Excel/PDF) يُبثّ في الردّ ولا يُحفظ،
و`core_storedfile` يحمل المرفوعاتِ (أعذاراً، أدلّةً، خطَّ PDF) لا مخرجاتٍ مؤقّتة. فلا قاعدةَ لها.

## 4. ما يُحفظ — كلُّ جدولٍ وسببُه

### 4.1 سجلُّ التدقيق والامتثال — يُحفظ كلُّه

| الجدول | لماذا |
|---|---|
| `core_auditlog` | سجلُّ التدقيق الرئيس؛ ثابتٌ بمشغّلٍ في القاعدة (م.19). ومنه `login_failed`/`mfa_failed` — انظر §5. |
| `core_permissionauditlog` | من غيّر صلاحيّةَ من ومتى — ثابتٌ بالتصميم. |
| `operations_permissionauditlog` | منحُ الصلاحيّات المؤقّتة وإلغاؤها. |
| `core_consentrecord` | الموافقةُ وسحبُها — دليلُ المشروعيّة (م.4). |
| `core_breachreport` | تقاريرُ الخرق وإخطارُ الجهة خلال 72 ساعة (م.11). |
| `core_erasurerequest` | طلباتُ المحو وملخّصُها المجهَّل (م.18) — دليلُ التنفيذ. |
| `django_admin_log` | أثرُ لوحة الإدارة. |
| `developer_feedback_auditlog` | أثرُ الوصول إلى صندوق المطوّر. |
| `developer_feedback_messagestatuslog` | تاريخُ حالة رسالة المطوّر. |
| `developer_feedback_messageedithistory` | تاريخُ تعديلها. |
| `developer_feedback_legalonboardingconsent` | موافقةٌ قانونيّةٌ على استعمال القناة. |
| `quality_procedurestatuslog` | تاريخُ حالة إجراءات الخطّة التشغيليّة. |

### 4.2 سجلّاتُ الطلبة — احتفاظٌ وزاريّ

السجلُّ الأكاديميّ والحضورُ والسلوكُ والصحّةُ تعود إليها الوزارةُ والمدرسةُ بعد سنوات (شهاداتٌ،
تظلّماتٌ، انتقالٌ). تُحذف بطلب محوٍ فرديٍّ مقبول أو بقرارٍ وزاريّ، لا بمرور الزمن.

| الجدول | ما فيه |
|---|---|
| `assessments_studentassessmentgrade` | درجاتُ التقييمات |
| `assessments_studentsubjectresult` | نتائجُ الفصول |
| `assessments_annualsubjectresult` | النتائجُ السنويّة |
| `core_studentenrollment` | القيدُ في الشعب |
| `core_parentstudentlink` | ربطُ وليّ الأمر بالطالب وصلاحيّاتُه |
| `operations_studentattendance` | الحضورُ بالحصّة |
| `operations_sectiondayconfirmation` | تثبيتُ رصد الشعبة |
| `operations_periodconfirmation` | تثبيتُ رصد الحصّة |
| `operations_classexit` | الخروجُ من الفصل وعودتُه |
| `operations_absencealert` | تنبيهاتُ عتبات الغياب |
| `operations_absenceexcuse` | أعذارُ الغياب المقدَّمة للمشرف — جزءٌ من سجلّ الحضور |
| `core_behaviorinfraction` | المخالفاتُ السلوكيّة |
| `core_behaviorpointrecovery` | استعادةُ النقاط |
| `core_healthrecord` | الملفُّ الصحّيّ (مشفَّر) |
| `core_clinicvisit` | زياراتُ العيادة |
| `student_affairs_studentactivity` | الأنشطةُ الطلّابيّة |
| `student_affairs_studenttransfer` | الانتقالُ بين الشعب |
| `student_info_studentnote` | ملاحظاتُ الجهات الخمس |
| `core_bookborrowing` | الإعاراتُ — تُطالَب المكتبةُ بها |
| `core_libraryactivity_participants` | المشاركةُ في أنشطة المكتبة |
| `core_busroute_students` | تسكينُ الطلبة على الخطوط |
| `exam_control_examincident` | حوادثُ الاختبارات — تظلّمات |

### 4.3 سجلّاتُ الموظّفين — مدّةُ الخدمة وما بعدها

| الجدول | ما فيه |
|---|---|
| `core_customuser` | الحسابُ نفسُه (الرقمُ الشخصيّ مشفَّرٌ بـHMAC+Fernet). `residence_area` وحدَه مدّتُه مدّةُ الخدمة — انظر §5. |
| `core_customuser_groups` | ربطُ Django |
| `core_customuser_user_permissions` | ربطُ Django |
| `core_profile` | الملفُّ الشخصيّ |
| `core_membership` | العضويّةُ والدور — والمطفأةُ تاريخُ خدمة |
| `core_role` | الأدوار |
| `staff_affairs_leavebalance` | أرصدةُ الإجازات |
| `staff_affairs_leaverequest` | طلباتُ الإجازات |
| `staff_affairs_staffattendance` | حضورُ الموظّف اليوميّ: الحالةُ ووقتا الحضور والانصراف ودقائقُ التأخّر والانصراف المبكر والإذن، ونوعُ يوم الغياب والعذرُ المقبول (نصٌّ حرٌّ قصير) — سندُ الخصم (سياسة الحضور ت/د 2027/01، البنود 2.4 و5.1–5.3) |
| `staff_affairs_permitrequest` | طلباتُ الأذونات القصيرة واعتمادُها (نموذج 02) — رصيدُ الساعات الشهريّ يُحسب منها |
| `operations_staffevaluation` | تقييمُ الأداء |
| `quality_employeeevaluation` | تقييمُ الموظّف |
| `quality_evaluationscore` | درجاتُ المقيِّمين |
| `quality_classroomobservation` | الزياراتُ الصفّيّة |
| `quality_observationscore` | درجاتُها |
| `quality_qualitycommitteemember` | عضويّةُ لجنة الجودة |
| `quality_executormapping` | ربطُ المنفّذين |
| `operations_teacherabsence` | غيابُ المعلّمين |
| `operations_substituteassignment` | البدلاء |
| `operations_teacherswap` | التبديلات |
| `operations_compensatorysession` | الحصصُ التعويضيّة |
| `operations_temporarypermission` | الصلاحيّاتُ المؤقّتة — مع سجلّها |
| `operations_teacherexemption` | التفريغات |
| `operations_teacherpreference` | تفضيلاتُ الجدول |
| `exam_control_examsupervisor` | إشرافُ الكنترول |
| `academic_management_teacherworkloadplan` | خطّةُ النصاب |
| `academic_management_teacherworkloadallocation` | توزيعُه |
| `academic_management_workloadgovernance` | حوكمةُ الأنصبة |
| `academic_management_curriculumplan` | الخطّةُ الدراسيّة |
| `academic_management_coursepreparation` | إسنادُ التحضير |

### 4.4 البنيةُ الأكاديميّةُ والتشغيليّة — لا مدّةَ لها

مرجعُ المدرسة (الأعوامُ والشعبُ والموادُّ والجداول) وإعداداتُها. أكثرُها بلا بياناتٍ شخصيّة،
وما يذكر معلّماً يذكره بصفته الوظيفيّة داخل جدولٍ معتمَد.

| الجدول | ما فيه |
|---|---|
| `core_school` | المدرسةُ نفسُها |
| `core_academicyear` | الأعوام |
| `core_semester` | الفصول |
| `core_calendarevent` | التقويم |
| `core_classgroup` | الشعب |
| `core_department` | الأقسام |
| `assessments_assessmentpackage` | باقاتُ التقييم (P1–P4) |
| `assessments_assessment` | التقييماتُ المعرَّفة |
| `assessments_subjectclasssetup` | إعدادُ المادّة للشعبة |
| `core_timeband` | نطاقاتُ التوقيت |
| `core_wing` | الأجنحة |
| `core_wingcoverage` | تغطيتُها |
| `operations_subject` | الموادّ |
| `operations_session` | الحصصُ اليوميّة |
| `operations_scheduleslot` | خانةُ الجدول |
| `operations_subjectclassassignment` | الإسناد |
| `operations_schedulingresource` | مواردُ الجدولة |
| `operations_schedulingresource_subjects` | ربطُها بالموادّ |
| `operations_schedulebaseline` | الأساسُ المرجعيّ |
| `operations_scheduleconstraintoverride` | استثناءاتُ القيود |
| `operations_schedulegeneration` | عمليّاتُ التوليد |
| `operations_freeslotregistry` | الحصصُ الحرّة |
| `operations_timeslotconfig` | الحصصُ الزمنيّة |
| `exam_control_examsession` | دوراتُ الاختبار |
| `exam_control_examroom` | القاعات |
| `exam_control_examschedule` | جدولُ الاختبار |
| `exam_control_examenvelope` | محاضرُ المظاريف |
| `exam_control_examgradesheet` | أوراقُ الرصد |
| `core_librarybook` | الكتب |
| `core_libraryactivity` | أنشطةُ المكتبة |
| `core_schoolbus` | الحافلات — اسمُ السائق ورقمُه بيانا مورّدٍ حيّ |
| `core_busroute` | الخطوط |
| `behavior_violationcategory` | فئاتُ المخالفات |
| `quality_operationaldomain` | مجالاتُ الخطّة |
| `quality_operationaltarget` | أهدافُها |
| `quality_operationalindicator` | مؤشّراتُها |
| `quality_operationalprocedure` | إجراءاتُها |
| `quality_procedureevidence` | أدلّتُها |
| `quality_observationcriterion` | معاييرُ الزيارة |
| `quality_evaluationcycle` | دوراتُ التقييم |
| `quality_roleevaluationtemplate` | قوالبُ التقييم |
| `quality_evaluationaxis` | محاورُها |
| `notifications_notificationsettings` | إعداداتُ الإشعارات (بيانات Twilio مشفَّرة) |
| `notifications_usernotificationpreference` | تفضيلاتُ المستخدم — تعيش مع حسابه |
| `core_storedfile` | المرفوعات: أعذارٌ وأدلّةٌ وخطُّ PDF. تُحذف بحذف مرجعها أو بطلب محو (`erasure_service`). |

### 4.5 المنصّة — بلا بياناتٍ شخصيّة أو قناةٌ مقصودةٌ عابرةٌ للمدارس

| الجدول | لماذا |
|---|---|
| `auth_group` | مجموعاتُ Django |
| `auth_group_permissions` | ربط |
| `auth_permission` | فهرسُ الصلاحيّات |
| `django_content_type` | فهرسُ النماذج |
| `developer_feedback_developermessage` | رسائلُ المطوّر — قناةٌ عابرةٌ للمدارس، ولها محوٌ داخلها |
| `developer_feedback_developermessagenotification` | إشعاراتُها |

## 5. قراراتٌ معلّقةٌ عند المالك

1. **`login_failed` و`mfa_failed` في `core_auditlog`**: طُلب حذفُهما بعد N، لكنّ الجدولَ ثابتٌ
   بمشغّلٍ في القاعدة (`0014`/`0059`) وبمديره، والسياسةُ نفسُها تقول «سجلُّ التدقيق كلُّه
   يُحفظ». فأُبقيا، ويُحذف نظيرُهما في `axes_*`. ولو أُريد حذفُهما لزم استثناءٌ صريحٌ في
   المشغّل لهذين الفعلين وحدَهما بعد N — قرارٌ يُتّخذ لا يُفترض.
2. **الرسائلُ الفاشلةُ غيرُ المحلولة** (`notifications_deadlettermessage`, `resolved=false`)
   أقدمُ من N: تبقى لأنّها طابورُ مشغّل. إن أراد المالك حذفَها بعد المدّة فسطرٌ واحد.
3. **`core_customuser.residence_area`**: مدّتُه المعلَنةُ مدّةُ الخدمة («يُفرَّغ عند إنهائها»)،
   و`record_staff_departure` لا يُفرِّغه اليوم. حذفٌ بحدثٍ لا بزمن — خارجَ هذه المهمّة، ويُقرَّر.
4. **المدّةُ نفسُها**: 730 افتراضٌ هندسيّ (عامان دراسيّان) لا رقمٌ وزاريّ. يُثبَّت بقرار
   مسؤول حماية البيانات ويُضبط في Railway على خدمة العامل.
