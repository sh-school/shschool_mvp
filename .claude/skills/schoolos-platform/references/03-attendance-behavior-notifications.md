# 03 — الحضور والسلوك والإشعارات

> متى تقرأ هذا الملف: قبل لمس رصد الحضور أو الغياب أو التأخّر، أو المخالفات وسلالمها، أو إرسال إشعارٍ لوليّ أمرٍ أو موظّف.
> الأرقامُ من ثوابت الشيفرة على `main@81bc4937`؛ ونصُّ الدليل الوزاريّ عند مهارة schoolos-source-of-truth.

## الحصصُ والحضور (`operations/models/attendance.py`)
- `Session` — حصّةٌ يوميّة: `school, class_group, teacher, subject, date, start_time, end_time, period_number, status`. تُولَّد من الجدول الأسبوعيّ (`ScheduleSlot`)، ومنها `SessionAutoGenerateMiddleware` في `operations/middleware.py`.
- `StudentAttendance(session, student, school, status, whereabouts, source, excuse_type, excuse→AbsenceExcuse, tardiness_minutes)`:
  - `status`: present, absent, late, excused.
  - `whereabouts` (أين هو وإن لم يكن غائباً): clinic, activity, out_permit, out_no_permit, left_early, gate.
  - `source` (من رصد): teacher, supervisor, gate, clinic, system…
  - `excuse_type`: القائمةُ المغلقة الخمس — medical, bereavement, family, state_representation, official — و`other` للقديم قبلها فقط.
- وغيرُها: `AbsenceExcuse` (العذرُ ووثيقتُه)، `GuardianContact`، `AbsenceAlert(absence_count, gate, status ∈ pending|notified|resolved)`، `SectionDayConfirmation`، `PeriodConfirmation`، `ClassExit`. وملفُّ الغياب والتقارير في `operations/absence_file.py` و`daily_absence.py` و`period_register.py`، وسجلُّ الجناح في `wings/`.

## عتباتُ الغياب والتأخّر (`operations/absence_policy.py`)
المصدر فيه: الدليل التنظيميّ لسياسة إدارة سلوك الطلبة 2026 (3.4.1.3 ص29، 3.4.2.2 ص33، 3.4.3 ص34، 3.7.3.3 ص139–140). الدليلُ ألغى أرقام 2018 (7·10·13·15).

| النطاق | العتبات (أيّامُ غيابٍ بلا عذر) | الثابت |
|---|---|---|
| الصفوف 1–11 | 5 · 8 · 11 · 15 (منتصف ف1، نهاية ف1، منتصف ف2، نهاية ف2) | `GATES_1_11` |
| الصفّ 12 | 8 · 15 (عتبتا النهاية فقط) | `GATES_12` |
| ذوو الإعاقة | 8 · 15 بسلّم استدعاءٍ أضيق | `GATES_ESE` |

- **الدلالةُ «تجاوز» لا «بلوغ»:** من غاب خمسةً لم يُحرم، ومن غاب ستّةً حُرم (`max_days` = المسموح). استعمل `next_gate()` و`breached()` لا مقارنةً يدويّة.
- **الوحدةُ تحسب ولا تُنفّذ:** الحرمانُ قرارُ فريق إدارة سلوك الطلبة؛ المنصّةُ تعرض وتُنذر (`ExamDeprivation` يُسجّل القرار).
- `TARDIES_PER_ABSENCE_DAY = 7` — التأخّرُ السابعُ يومُ غيابٍ كامل **يدخل في حساب العتبات** (`absence_days_from_tardies`).
- `TARDY_AFTER_MINUTES = 15` (الطابور، نصّ)، و`PERIOD_TARDY_AFTER_MINUTES = 5` و`PERIOD_RECORDING_GRACE_MINUTES = 5` **قراراتُ المدرسة** 2026-09-13 لا نصّ.
- `MIN_PERIODS_FOR_PRESENCE = 4` (من استأذن قبلها فيومُه غياب)، و`MEDICAL_PROOF_DAYS_AFTER_RETURN = 2` (من العودة لا من الغياب)، و`GUARDIAN_REPLY_DAYS = 2`.
- قراراتُ ملفّ الغياب والعتبات المؤكَّدة: ذاكرة `project_absence_thresholds_confirmed.md` و`project_absence_file_decisions.md`.

## السلوك (`behavior/`)
- **الدليلُ 2026 = 41 مخالفة:** الأولى 9، الثانية 7، الثالثة 10، الرابعة 15 (والتنمّرُ 17 منها). المصدر: `behavior/conduct_2026.py` (جدولُ ص84؛ كان الاستخراجُ الأوّل 44 خطأً، ودليلُ 2025 القديم 40). الحقنُ: `python manage.py seed_violations_2026`.
- `ViolationCategory(degree 1..4, code "1-01".."4-15", name_ar, points, ladder_key, ladder_json, requires_security_referral, requires_parent_summon, tags)`؛ و`category` A–D حقلٌ قديمٌ لما قبل 2025.
- `BehaviorInfraction(student, violation_category, level, escalation_step, points_deducted, session, ...)` — حقولُ الدرجة الثالثة (`social_media_platform`، `digital_evidence_notes`) والرابعة (`security_referral_date`، `security_agency`، `security_reference_number`)؛ والنصوصُ الحسّاسة `EncryptedTextField` (`violation_description`، `digital_evidence_notes`، `security_notes`). جدولُه `core_behaviorinfraction`.
- `BehaviorPointRecovery` (استعادةُ النقاط بموافقة اللجنة)، `AutoInfractionNotice`.
- **السلّمُ مشترك** بين مخالفاتٍ، والتكرارُ يُعدّ **لكلّ مخالفةٍ على حدة** لا لكلّ سلّم. **قراراتُ المدرسة** (2026-09-13؛ الدليلُ صامت): العدّادُ يُصفَّر كلَّ فصل، والمخالفةُ مرّتين في اليوم نفسه تكراران. التنفيذ: `BehaviorService.suggest_escalation_step` و`get_prior_infraction_count` (`behavior/services.py`).
- ما بعد السلّم: الإحالةُ كما ينصّ جدولُ المخالفة، وما لا ينصّ عليه يبقى فارغاً ولا يُخترع.
- **الأسماءُ تُنسخ إلى القاعدة مرّةً** (هجرة `0015_conduct_catalog_2026`): تصحيحُ `name_ar` أو `points` في `CATALOG` وحده لا يصل الإنتاج — يلزمه هجرةُ بياناتٍ خفيفة؛ أمّا السلالمُ فتُقرأ من الشيفرة. المصدر: ذاكرة `project_conduct_catalog_db_names_need_migration.md`.
- الصلاحيّاتُ: `BEHAVIOR_RECORD` و`BEHAVIOR_MANAGE` و`BEHAVIOR_COMMITTEE` في `core/permissions.py`، و`BehaviorPermissions` في `behavior/services.py`.

## الإشعارات (`notifications/`)
- **مدخلٌ واحد:** `notifications.hub.NotificationHub.dispatch(event_type, school, recipients, title, body, context, priority, related_url)`، و`dispatch_to_role` و`dispatch_to_parents`. يُنشئ `InAppNotification` فوراً ويوزّع الخارجيَّ عبر Celery، ويحترم التفضيلات وساعاتِ الهدوء (`quiet_hours.py`).
- **القنوات:** in_app، push (VAPID)، email، sms، whatsapp (Twilio، ومفاتيحُه مشفّرةٌ في `NotificationSettings`). القناةُ الخارجيّة لا تُطلب لمن لا عنوانَ له (`channels.py::deliverable_external_channels`). الافتراضاتُ لكلّ حدثٍ `DEFAULT_CHANNELS` في `hub.py`.
- **الموافقةُ صريحة** (قرار المالك 2026-09-21، PDPPL): أحداثُ وليّ الأمر الاختياريّة (سلوك، درجات، رسوب، صحّة) لا تصل إلّا بموافقةٍ مسجَّلة، والسحبُ الصريح يغلب؛ وأحداثُ الخدمة الإلزاميّة (غياب، استدعاء، إرسالٌ إلى البيت) تصل دائماً. المصدر: `hub.py::_filter_consent`، `ConsentRecord`.
- **مسارُ التسليم المتتبَّع** (`NotificationDispatch` → `NotificationDelivery` + `NotificationEnqueueIntent`) خلف راية `NOTIFICATION_HUB_DELIVERY_PIPELINE_ENABLED` — «مطفأةٌ افتراضياً وفي الإنتاج» بنصّ تعليق `_tracked_pipeline_enabled`. والرسائلُ الفاشلة نهائيّاً `DeadLetterMessage`.
- الأولويّة: low, medium, high, urgent. وإخطاراتُ الخرق `BreachNotificationService` في `notifications/services.py`.

## أنماطٌ مضادّة
- حسابُ العتبة بـ`>=` أو نسيانُ أيّام التأخّر السبعة فيها.
- عذرٌ خارج القائمة الخمس «باجتهاد مدرسيّ».
- حرمانٌ آليٌّ من الاختبار عند بلوغ العدد — العرضُ والإنذارُ فقط، والقرارُ للفريق.
- `InAppNotification.objects.create(...)` أو إرسالُ بريدٍ مباشرةً من view بدل `NotificationHub` — يتجاوز الموافقةَ والتفضيلاتِ وساعاتِ الهدوء.
- تعديلُ اسم مخالفةٍ في `conduct_2026.py` وحده وانتظارُ ظهوره في الإنتاج.
