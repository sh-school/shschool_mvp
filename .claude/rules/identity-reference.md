---
paths:
  - "static/**"
  - "templates/**"
  - "core/templatetags/ui.py"
  - "core/icons.py"
---

# مرجعُ الهويّة المولَّد: أنماط الصفحات والأيقونات

> مولَّدٌ آليّاً من `static/css/custom/` و`core/icons.py` و`docs/design/page_layouts.md` — لا يُحرَّر بيدٍ؛ أعِد توليده بـ`python scripts/gen_identity_reference.py`. يقوم مقامَ صفحات `/styleguide/` لمن لا حسابَ مطوّر له.
> القاعدة: لونٌ برمزٍ لا بقيمة، وأيقونةٌ بمعناها `{% icon "المفتاح" %}`، وصفحةٌ بنمطٍ مسمّى `{% page_layout "…" %}`.
> جداولُ الألوان في `identity-colours-core.md` (الهويّة والنصّ والترويسة والحالات) و`identity-colours-more.md` (التمييز والرسوم والأدوار).

## أنماط الصفحات السبعة

- `layout-dashboard` (لوحة): نظرةٌ واحدةٌ على الحال لصاحب دورٍ، تُقرأ بلا تمرير على `expanded`.
- `layout-hub` (مدخلُ وحدة): صفحةُ الدخول إلى وحدةٍ فيها وظائف كثيرة، يختار منها المستخدم.
- `layout-list` (سجلّ): قائمةُ سجلّاتٍ للبحث والتصفية والفتح.
- `layout-detail` (تفصيل): سجلٌّ واحدٌ بكلّ ما يتعلّق به (طالب، موظّف، بلاغ، زيارة).
- `layout-form` (نموذج): إدخالُ سجلٍّ أو تعديلُه.
- `layout-sheet` (ورقةٌ كثيفة): شبكةٌ من صفوفٍ وأعمدةٍ كثيرة تُقرأ وتُحرَّر في مكانها.
- `layout-report` (تقرير): وثيقةٌ تُقرأ ثمّ تُصدَّر أو تُطبع ورقاً (قرارُ المالك: الكشوفُ الورقيّة تبقى قابلةً للطباعة).

## قاموس الأيقونات (بالمعنى لا بالشكل)

**وحدات المنصّة** (42): `quality` الجودة والخطّة التشغيليّة؛ `behavior` السلوك؛ `dashboard` لوحة التحكّم؛ `library` المكتبة؛ `grades` الدرجات وكشوفها؛ `notifications` الإشعارات؛ `transport` النقل المدرسيّ؛ `observation` الزيارات الصفّيّة؛ `assessments` التقييمات والاختبارات؛ `clinic` العيادة المدرسيّة؛ `staff` شؤون الموظفين؛ `student_info` مركز معلومات الطلبة؛ `wings` أجنحة المدرسة؛ `security` الأمان والصلاحيات؛ `workload` الإسناد والأنصبة؛ `activities` الأنشطة؛ `periods_today` حصص اليوم (حيّة)؛ `schedule` الجدول الدراسي؛ `academic` الشؤون الأكاديميّة والموادّ؛ `parents` أولياء الأمور؛ `breach` خرق البيانات (PDPPL)؛ `messages` الرسائل والبريد؛ `counseling` الإرشاد الاجتماعيّ والنفسيّ؛ `developer` المساعد والمطوّر؛ `exam_control` الكنترول؛ `services` الخدمات المدرسيّة؛ `my_actions` إجراءاتي؛ `plan_execution` تنفيذ الخطّة؛ `self_review` المراجعة الذاتيّة؛ `plan_committee` لجنة منفّذي الخطّة؛ `review_committee` لجنة المراجعة الذاتيّة؛ `staff_register` سجلّ الموظفين؛ `departments` الأقسام التعليميّة؛ `exam_analytics` تحليلات الاختبارات؛ `observation_reports` تقارير الأداء الصفّيّ؛ `elearning` التعليم الإلكترونيّ؛ `mail_unread` الرسائل الجديدة؛ `mail_sent` الرسائل المرسلة؛ `password` كلمة المرور؛ `two_factor` المصادقة الثنائيّة؛ `dev_inbox` صندوق رسائل المطوّر؛ `roadmap` خارطة تجويد المنصّة

**الحياة المدرسيّة** (29): `reinforcement` التعزيز الإيجابيّ؛ `psychology` الأخصائي النفسيّ؛ `behavior_team` فريق سلوك الطلبة؛ `wing_coverage` تغطية الأجنحة والإنابة؛ `absence` الغياب؛ `behavior_violation` مخالفة سلوكيّة (بالدرجة)؛ `attendance_register` رصد الحضور؛ `swap_requests` طلبات التبديل والتنقّلات؛ `behavior_committee` لجنة الضبط والقرار؛ `leave` الإجازات؛ `tardiness` التأخّر؛ `attendance_teacher_absence` غياب المعلّمين والبدلاء؛ `compensation` الحصص التعويضيّة؛ `staff_evaluation` تقييم أداء الموظفين؛ `failing_students` الطلاب المتعثّرون والراسبون؛ `licences` الرخص المهنيّة؛ `bells` التوقيت والأجراس؛ `clinic_visit` زيارة الطالب للعيادة؛ `exemptions` تفريغات المعلّمين؛ `sent_home` استئذان وإرسال للمنزل؛ `restroom` دورة المياه؛ `substitution` تعيين بديل؛ `arabic_subject` اللغة العربيّة؛ `certificates` الشهادات؛ `islamic_ed` التربية الإسلاميّة؛ `prayer` الصلاة والمصلّى؛ `qr_door` رمز باب الشعبة؛ `injury` الإصاباتُ والأضرار؛ `grade_sheets` أوراقُ الرصد والتصحيح

**الكيانات** (7): `students` الطلاب والشُّعب؛ `profile` الملفّ الشخصيّ؛ `children` أبنائي (بوّابة الوليّ)؛ `school_building` المدرسة؛ `teacher` المعلّم؛ `student` الطالب؛ `supervisors` مشرفو الكنترول

**البيانات والتقارير** (10): `location` الموقع والخريطة؛ `stats` الإحصائيّات والتوزيعات؛ `checklist` قائمة بنود؛ `document` مستند؛ `reports` التقارير؛ `date` التاريخ والتقويم؛ `kpi` مؤشّرات الأداء؛ `trend` الاتّجاه عبر الزمن؛ `folder` مجلّد؛ `policy` اللوائح والقرارات الرسميّة

**الأفعال** (25): `edit_record` تحرير سجلّ / ملاحظة؛ `print` طباعة؛ `confirm` تأكيد؛ `export_excel` تصدير Excel؛ `export_pdf` تصدير PDF؛ `refresh` تحديث / إعادة؛ `add` إضافة؛ `search` بحث؛ `import` استيراد؛ `call_parent` استدعاء وليّ الأمر؛ `save` حفظ؛ `delete` حذف؛ `generate` توليد تلقائيّ؛ `link` الربط؛ `student_add` إضافة طالب؛ `download` تنزيل؛ `all_present` الكلّ حاضر؛ `filter` تصفية؛ `upload` رفع؛ `edit` تعديل؛ `user_add` إضافة مستخدم؛ `view` عرض؛ `attach` مرفق؛ `calculate` حساب؛ `user_remove` إزالة مستخدم

**الحالات والتنبيهات** (11): `status_warning` تحذير؛ `status_success` نجاح / مكتمل؛ `status_error` خطأ / مرفوض؛ `time` الوقت والمهلة؛ `status_info` معلومة؛ `empty` لا بيانات؛ `loading` جارٍ التحميل؛ `status_critical` حرِج / عاجل؛ `offline` لا اتّصال؛ `status_blocked` محظور / غير متاح؛ `tip` تلميح

**هيكل الواجهة** (12): `settings` الإعدادات؛ `back` رجوع؛ `close` إغلاق؛ `maintenance` صيانة وأدوات؛ `next` التالي؛ `prev` السابق؛ `theme_dark` الوضع الليليّ؛ `install_app` تثبيت التطبيق؛ `logout` تسجيل الخروج؛ `menu` القائمة؛ `role_switch` تبديل الدور؛ `theme_light` الوضع النهاريّ
