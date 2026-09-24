"""مزامنةُ الخارطة 0010: 23 بنداً كُتبت في لقطة claude.ai ولم تصل المنصّة (OWN-09..OWN-30 وDONE-26).

جلساتٌ سجّلت بنودَ الإدارة وقراراتِ المالك في لقطة الـArtifact (`claude.ai/artifact/53pQUyt56HdmABwurHmtBN`)
بعد استيراد الخارطة إلى المنصّة (0001)، فبقيت الخارطةُ الحيّةُ على OWN-01..OWN-08 وحدها. هذه تنقلها كما هي
في اللقطة يومَ 2026-09-24، إلّا:

- **OWN-26 وOWN-27 وOWN-28** «قيد الدمج في #477» في اللقطة، و#477 اندمج ونُشر يومَ 2026-09-22 — فتُنقل مُغلقة.
- **OWN-20** «لم يبدأ» في اللقطة، وهو منجزٌ منذ #298 (2026-09-17): دخولُ الإدارة يُحوَّل إلى دخول المنصّة.
- **OWN-25 وDONE-26** فيها أسماءُ موظّفين وأرقامٌ وظيفيّةٌ وصيغةُ كلمة المرور المؤقّتة للكادر — **لم تُنقل**:
  المستودعُ عامّ (قاعدةُ «لا رقمَ شخصيّاً حقيقيّاً في شيفرةٍ متتبَّعة»)، والصيغةُ تُسهّل تخمينَ كلمة مرور من لم يغيّرها.

تُنشأ البنودُ إن غابت ولا يُكتب فوق موجود — فلو أضافها المطوّرُ من الصفحة قبلها بقي ما أضافه.
"""

import datetime

from django.db import migrations

#: البنودُ كما في اللقطة يومَ 2026-09-24 (مولَّدةٌ منها، بعد التنقية أعلاه).
ITEMS = [
    {
        "code": "OWN-09",
        "src": "OWN",
        "lane": "desktop",
        "title": "لوحة الإدارة بهويّة المنصّة: ألوانُها النهاريّة والليليّة وخطّ Tajawal وأيقونتُها، واسمُ المدرسة "
        "وشعارُها في الترويسة",
        "status": "done",
        "progress": 100,
        "start": "2026-09-20",
        "end": "2026-09-21",
        "basis": "منجز",
        "effort": 1,
        "deps": "",
        "criterion": "حارسُ انجرافٍ يفشل إن تباعدت الألوانُ عن رموز المنصّة",
        "note": "",
        "gate": "",
        "ref": "#460 · جلسة تقييم الهويّة البصريّة",
        "pr": "",
    },
    {
        "code": "OWN-10",
        "src": "OWN",
        "lane": "desktop",
        "title": "لوحة الإدارة: قائمةٌ أفقيّةٌ في الترويسة بثماني مجموعاتٍ لكلّ نماذجها (97) وتذييلُ المنصّة "
        "الدائم",
        "status": "done",
        "progress": 100,
        "start": "2026-09-20",
        "end": "2026-09-21",
        "basis": "منجز",
        "effort": 1,
        "deps": "OWN-09",
        "criterion": "كلُّ نموذجٍ مسجَّلٍ في مجموعةٍ واحدة بحارسٍ؛ قائمةٌ واحدةٌ مفتوحةٌ في المرّة",
        "note": "",
        "gate": "",
        "ref": "#460 · جلسة تقييم الهويّة البصريّة",
        "pr": "",
    },
    {
        "code": "OWN-11",
        "src": "OWN",
        "lane": "desktop",
        "title": "لوحة الإدارة: أقسامُ التطبيقات قابلةٌ للطيّ ومطويّةٌ افتراضياً، وتصحيحُ أربعةِ أسماءٍ عربيّةٍ في "
        "القالب",
        "status": "done",
        "progress": 100,
        "start": "2026-09-20",
        "end": "2026-09-21",
        "basis": "منجز",
        "effort": 0.5,
        "deps": "",
        "criterion": "",
        "note": "الأسماءُ الخاطئةُ تبقى في النماذج نفسِها بقرار المالك (لا مساسَ بالمنصّة)",
        "gate": "",
        "ref": "#460 · جلسة تقييم الهويّة البصريّة",
        "pr": "",
    },
    {
        "code": "OWN-12",
        "src": "OWN",
        "lane": "desktop",
        "title": "رئيسيّةُ الإدارة: ثماني بطاقاتِ مراقبةٍ للمطوّر (الصحّة، العامل، الأمان، الإشعارات، الإجراءات "
        "الحسّاسة، الهجرات، ملاحظات المطوّر، الخارطة)",
        "status": "done",
        "progress": 100,
        "start": "2026-09-21",
        "end": "2026-09-21",
        "basis": "منجز",
        "effort": 1,
        "deps": "OWN-10",
        "criterion": "للمطوّر وحده، مرتّبةٌ بالأخطر، بلا جدولٍ جديد",
        "note": "التنبيهُ بالبريد/الهاتف/الواتساب مؤجَّلٌ لحين تشغيلها",
        "gate": "",
        "ref": "#465 · جلسة تقييم الهويّة البصريّة",
        "pr": "",
    },
    {
        "code": "OWN-13",
        "src": "OWN",
        "lane": "sec",
        "title": "الإدارة: ستر كلِّ رقمٍ من ثمانيةِ أرقامٍ فأكثر في «آخر الإجراءات» (رقمٌ شخصيٌّ في نصّ سجلّ "
        "التدقيق) — PDPPL",
        "status": "done",
        "progress": 100,
        "start": "2026-09-21",
        "end": "2026-09-21",
        "basis": "منجز",
        "effort": 0.25,
        "deps": "",
        "criterion": "في قالب الإدارة فقط؛ سجلُّ التدقيق نفسُه لم يُمسّ",
        "note": "",
        "gate": "",
        "ref": "#465 · جلسة تقييم الهويّة البصريّة",
        "pr": "",
    },
    {
        "code": "OWN-14",
        "src": "OWN",
        "lane": "desktop",
        "title": "الإدارة: تخطيطٌ بلا تمريرٍ رأسيٍّ للصفحة (منطقةُ المحتوى تمرّر داخلَها) وأقسامٌ بثلاثة أعمدة، "
        "و«آخر الإجراءات» بثلاثة أعمدة",
        "status": "done",
        "progress": 100,
        "start": "2026-09-21",
        "end": "2026-09-21",
        "basis": "منجز",
        "effort": 0.5,
        "deps": "OWN-12",
        "criterion": "قِيس على 1366×768: ارتفاعُ الصفحة = ارتفاعُ النافذة",
        "note": "",
        "gate": "",
        "ref": "#465 · جلسة تقييم الهويّة البصريّة",
        "pr": "",
    },
    {
        "code": "OWN-15",
        "src": "OWN",
        "lane": "desktop",
        "title": "الإدارة: 25 صفّاً في كلّ قائمةٍ بحارس، وإصلاحُ الجوّال (375px)، وشريطُ حفظٍ ثابت، وتذييلٌ بسطرٍ "
        "واحد، وحقولُ النماذج بعمودين",
        "status": "done",
        "progress": 100,
        "start": "2026-09-21",
        "end": "2026-09-22",
        "basis": "منجز",
        "effort": 1,
        "deps": "OWN-14",
        "criterion": "لا نموذجَ بغير 25 (حارسٌ يمنع الشذوذ)",
        "note": "لم يُقَس الوضعُ الليليّ بعدُ",
        "gate": "",
        "ref": "#470 · جلسة تقييم الهويّة البصريّة",
        "pr": "",
    },
    {
        "code": "OWN-16",
        "src": "OWN",
        "lane": "frontend",
        "title": "صفحةُ «لا عضويّة نشطة» بصفحة الخطأ الموحّدة وزرّ خروج، وذيلُ المنصّة ورقمُ هاتف المدرسة في بطاقة "
        "الدخول",
        "status": "done",
        "progress": 100,
        "start": "2026-09-21",
        "end": "2026-09-22",
        "basis": "مقترَح",
        "effort": 1,
        "deps": "",
        "criterion": "زرّ الخروج يعمل (مسارٌ POST)؛ لا {% static %} في صفحة الخطأ (حارسُ نشرٍ آمن)",
        "note": "دُمج ونُشر 2026-09-22 (#471 → main@4fbbd5bf)",
        "gate": "",
        "ref": "#471 · جلسة تقييم الهويّة البصريّة",
        "pr": "",
    },
    {
        "code": "OWN-17",
        "src": "OWN",
        "lane": "desktop",
        "title": "الإدارة: بحثٌ سريعٌ في القائمة العلويّة للوصول إلى أيّ نموذجٍ من 97 (اختصارُ لوحة المفاتيح /)",
        "status": "done",
        "progress": 100,
        "start": None,
        "end": "2026-09-22",
        "basis": "منجز",
        "effort": 0.5,
        "deps": "",
        "criterion": "",
        "note": "فهرسٌ مُضمَّنٌ (json_script) بلا طلبٍ إضافيّ؛ Enter يفتح أوّل نتيجة، / يُركّز الحقل. CodeQL وجد "
        "ثغرةٌ حقيقيّةٌ فيه (DOM text reinterpreted as HTML، a.href بلا تحقق) أُصلحت بتحقق isSafeAdminUrl "
        "(^/admin/ فقط) قبل الدمج.",
        "gate": "",
        "ref": "#475 · جلسة تقييم الهويّة البصريّة",
        "pr": "",
    },
    {
        "code": "OWN-18",
        "src": "OWN",
        "lane": "desktop",
        "title": "الإدارة: تعريبُ أسماء تطبيقات الطرف الثالث (AXES وTOKEN BLACKLIST) في قالب الإدارة",
        "status": "done",
        "progress": 100,
        "start": None,
        "end": "2026-09-22",
        "basis": "منجز",
        "effort": 0.25,
        "deps": "",
        "criterion": "",
        "note": "مرشّح app_label في app_list.html وحده (APP_LABELS)؛ الحزمتان نفسهما لم تُعدّلا.",
        "gate": "",
        "ref": "#475 · جلسة تقييم الهويّة البصريّة",
        "pr": "",
    },
    {
        "code": "OWN-19",
        "src": "OWN",
        "lane": "desktop",
        "title": "الإدارة: تعريبُ أسماء أعمدة القوائم والمرشّحات الإنجليزيّة (IS ACTIVE، DATE JOINED، «حسب is "
        "staff»)",
        "status": "todo",
        "progress": 0,
        "start": None,
        "end": None,
        "basis": "غير مجدول",
        "effort": 0.5,
        "deps": "",
        "criterion": "مصدرُها verbose_name في نماذج المنصّة",
        "note": "يحتاج قرارَ المالك بالمساس بالنماذج",
        "gate": "owner",
        "ref": "جلسة تقييم الهويّة البصريّة",
        "pr": "",
    },
    {
        "code": "OWN-20",
        "src": "OWN",
        "lane": "desktop",
        "title": "الإدارة: صفحةُ دخولِ الإدارة بهويّة المنصّة (الشعار واسمُ المدرسة والألوان وذيلُ المنصّة)",
        "status": "done",
        "progress": 100,
        "start": None,
        "end": None,
        "basis": "غير مجدول",
        "effort": 0.5,
        "deps": "",
        "criterion": "",
        "note": "[2026-09-24] منجزٌ سلفاً بـ#298 (2026-09-17، «دخولُ الإدارة من الباب الواحد»): /admin/login/ "
        "يُحوَّل إلى دخول المنصّة (core/mfa_session.py::admin_login_redirect) — نموذجُ Django لا يعرف الرمزَ "
        "الثنائيّ ولا القفل؛ فلا وجهَ لنموذج دخول الإدارة يُرى أصلاً. (تحقّقت جلسة الباك إند على الإنتاج: 302 إلى "
        "/auth/login/?next=/admin/.)",
        "gate": "",
        "ref": "جلسة تقييم الهويّة البصريّة",
        "pr": "#298",
    },
    {
        "code": "OWN-21",
        "src": "OWN",
        "lane": "desktop",
        "title": "الإدارة: فحصٌ بصريٌّ ليليّاً وعلى الجوّال (375px)، وأهدافُ اللمس 44px وتباينُ الألوان وترتيبُ "
        "التبويب",
        "status": "todo",
        "progress": 0,
        "start": None,
        "end": None,
        "basis": "غير مجدول",
        "effort": 0.5,
        "deps": "OWN-15",
        "criterion": "",
        "note": "لم يُقَس الوضعُ الليليّ بعد تعديلات #465 و#470",
        "gate": "",
        "ref": "جلسة تقييم الهويّة البصريّة",
        "pr": "",
    },
    {
        "code": "OWN-22",
        "src": "OWN",
        "lane": "frontend",
        "title": "توحيدُ ذيل المنصّة: مكوّنُ components/site_brand.html في base.html ولوحة الإدارة وصفحات الخطأ "
        "بدل النُّسَخ الثلاث",
        "status": "todo",
        "progress": 0,
        "start": None,
        "end": None,
        "basis": "غير مجدول",
        "effort": 0.5,
        "deps": "OWN-16",
        "criterion": "",
        "note": "الآن: نسخةٌ في base.html وأخرى في admin/_footer.html وثالثةٌ في site_brand.html",
        "gate": "",
        "ref": "جلسة تقييم الهويّة البصريّة",
        "pr": "",
    },
    {
        "code": "OWN-23",
        "src": "OWN",
        "lane": "ops",
        "title": "بطاقاتُ مراقبة المطوّر: مصدرُ أخطاء 5xx (Sentry) وآخرُ نسخةٍ احتياطيّة، والتنبيهُ عند اللون "
        "الأحمر بعد تشغيل هاتف المنصّة وبريدها وواتسابها",
        "status": "todo",
        "progress": 0,
        "start": None,
        "end": None,
        "basis": "غير مجدول",
        "effort": 1,
        "deps": "OWN-12",
        "criterion": "",
        "note": "النسخُ الاحتياطيّ خارجَ قاعدة البيانات (Railway وR2)؛ مؤجَّلٌ بقرار المالك",
        "gate": "owner",
        "ref": "جلسة تقييم الهويّة البصريّة",
        "pr": "",
    },
    {
        "code": "OWN-24",
        "src": "OWN",
        "lane": "debt",
        "title": "نقلُ roadmap/admin_menu.py وتعطيلِ الشريط الجانبيّ للإدارة إلى core/، وتحويلُ اختبار تغطية "
        "القائمة إلى تحذير",
        "status": "todo",
        "progress": 0,
        "start": None,
        "end": None,
        "basis": "غير مجدول",
        "effort": 0.5,
        "deps": "",
        "criterion": "",
        "note": "الآن: اختبارٌ يفشل عند تسجيل أيّ نموذجٍ جديدٍ دون تصنيفه",
        "gate": "",
        "ref": "جلسة تقييم الهويّة البصريّة",
        "pr": "",
    },
    {
        "code": "OWN-25",
        "src": "OWN",
        "lane": "sec",
        "title": "إخطار 127 عضو كادرٍ ببيانات دخولهم الجديدة — لم يُخطر أحدٌ بعد",
        "status": "todo",
        "progress": 0,
        "start": "2026-09-22",
        "end": "2026-09-29",
        "basis": "مقترَح",
        "effort": 0.5,
        "deps": "",
        "criterion": "الجميع أُخطروا وغيّروا كلمةَ المرور المؤقّتة؛ صفرُ حسابٍ باقٍ على كلمة المرور المؤقّتة بعد "
        "أسبوع",
        "note": "الأسماءُ والأرقامُ الوظيفيّةُ في لقطة claude.ai لم تُنقل (المستودعُ عامّ).",
        "gate": "owner",
        "ref": "جلسة claude/setup-wing-admin-accounts",
        "pr": "",
    },
    {
        "code": "OWN-26",
        "src": "OWN",
        "lane": "sec",
        "title": "نافذةٌ داخل المنصّة لفنّي تقنية المعلومات لإعادة تعيين كلمات مرور أيّ مستخدمٍ في مدرسته بدل "
        "/admin/، مقيّّدٌ بقدرة مسجّلة (core.capabilities)",
        "status": "done",
        "progress": 100,
        "start": "2026-09-22",
        "end": "2026-09-22",
        "basis": "منجز",
        "effort": 1,
        "deps": "",
        "criterion": "كلمةٌ عشوائيّةٌ (لا حقلَ حرّ)، تُعرض مرّةً واحدة، تُلزم بالتغيير، وتُسجّل في AuditLog بلا "
        "القيمة",
        "note": "البطاقةُ الوظيفيّةُ الوزاريّةُ تنسب حسابات المنصّة لمنسّق المشاريع الإلكترونيّة لا فنّي تقنية "
        "المعلومات، لكنّ المالك اختار حملها لهذا الدور فعلاً قرارٌ مدرسةٌ موثّق. قيد الدمج في #477 (269 "
        "اختباراً محليّاً نجحت، فحصان CI جارٍ). [2026-09-24] #477 اندمج ونُشر يومَ 2026-09-22.",
        "gate": "",
        "ref": "#477 · جلسة تقييم الهويّة البصريّة",
        "pr": "#477",
    },
    {
        "code": "OWN-27",
        "src": "OWN",
        "lane": "sec",
        "title": "صلاحيّاتُ المدير في /admin/: is_staff بمجموعةٍ صريحةٍ (core.admin_access) بدل is_superuser الذي "
        "كان يتجاوز كلّ حارسٍ في المنصّة بلا استثناء",
        "status": "done",
        "progress": 100,
        "start": "2026-09-22",
        "end": "2026-09-22",
        "basis": "منجز",
        "effort": 2,
        "deps": "",
        "criterion": "تعديلٌ كاملٌ على 11 نموذجَ إعدادٍ لا شاشةٌ له في المنصّة، قراءةٌ فقط على 12 نموذجَ تدقيق "
        "(منها CustomUser/Membership/Role عمداً بلا change لمنع تصعيدِ الصلاحيّة ذاتيّاً)، ولا شيءَ "
        "على الباقي (ن70 نموذجاً لها مسارٌ خدميٌّ في المنصّة، أو roadmap/developer_feedback للمطوّر "
        "فتسقط تلقائيّاً مع فقد is_superuser)",
        "note": "أمرٌ إدارةٌ جديد (scope_principal_admin_access --apply) لتطبيقه على حساب المدير الحقيقيّ بعد "
        "النشر قرارٌ منفصلٌ للمالك (OWN-29). قيد الدمج في #477 مع OWN-26. [2026-09-24] #477 اندمج ونُشر "
        "يومَ 2026-09-22.",
        "gate": "",
        "ref": "#477 · جلسة تقييم الهويّة البصريّة",
        "pr": "#477",
    },
    {
        "code": "OWN-28",
        "src": "OWN",
        "lane": "frontend",
        "title": "رسائلُ Django messages عائمةٌ فوق الصفحة (position: fixed) بخطٍّ مضاعَفٍ تقريباً وظلٍّ — تعديلٌ "
        "مركزيٌّ واحد يفيد كلّ صفحة",
        "status": "done",
        "progress": 100,
        "start": "2026-09-22",
        "end": "2026-09-22",
        "basis": "منجز",
        "effort": 0.25,
        "deps": "",
        "criterion": "معاينةٌ بمتصفّحٍ حقيقيّ نهاراً وليلاً وعلى الجوّال، بلا فيضان",
        "note": "static/css/custom/20-components.css (.msgs-wrap) لا شاشةٌ — يفيد كلّ صفحةٍ تستعمل "
        "messages.success/error في المنصّة، لا شاشة الإدارة. قيد الدمج في #477. [2026-09-24] #477 اندمج "
        "ونُشر يومَ 2026-09-22.",
        "gate": "",
        "ref": "#477 · جلسة تقييم الهويّة البصريّة",
        "pr": "#477",
    },
    {
        "code": "OWN-29",
        "src": "OWN",
        "lane": "ops",
        "title": "تشغيل scope_principal_admin_access --apply على حسابات المدير الحقيقيّة في الإنتاج بعد نشر #477 — "
        "يستبدل is_superuser بـis_staff والمجموعة الجديدة",
        "status": "todo",
        "progress": 0,
        "start": None,
        "end": None,
        "basis": "غير مجدول",
        "effort": 0.25,
        "deps": "OWN-27",
        "criterion": "عرضٌ أوّلاً (بلا --apply) في جلسة النشر، ثمّ --apply بإذن المالك",
        "note": "قرارٌ منفصلٌ لا ينفّذه أحدٌ من جلسات العمل إلاّ بإذنٍ صريح.",
        "gate": "owner",
        "ref": "جلسة تقييم الهويّة البصريّة",
        "pr": "",
    },
    {
        "code": "OWN-30",
        "src": "OWN",
        "lane": "debt",
        "title": "سقّاطةُ mypy تفشل على main نفسها الآن، بمعزلٍ عن أيّ فرعٍ من فروعي — نحوٌ 20 ملفّاً غير مرتبطٍ "
        "انجرفت أعدادُ أخطائها منذ آخر تسجيلٍ للخطّ الأساس",
        "status": "todo",
        "progress": 0,
        "start": None,
        "end": None,
        "basis": "غير مجدول",
        "effort": 1,
        "deps": "",
        "criterion": "تحديدٌ من لمس كلّ ملفٍّ ولماذا، ثمّ python -m tests.mypy_ratchet --update بعد إقرارٍ أو "
        "إصلاحٍ",
        "note": "منها: core/views_auth.py (17→12)، operations/departments.py (11→18)، staff_affairs/models.py "
        "(4→9)، operations/services/schedule_read.py (5→10)، وغيرها — لا علاقة لها بفروع الإدارة، ولم "
        "تُلمس.",
        "gate": "owner",
        "ref": "جلسة تقييم الهويّة البصريّة",
        "pr": "",
    },
    {
        "code": "DONE-26",
        "src": "DONE",
        "lane": "sec",
        "title": "تجهيز بيانات دخول الكادر على الإنتاج والمحلي: 127 حساباً (كلّ الأدوار عدا حساب المطوّر)",
        "status": "done",
        "progress": 100,
        "start": None,
        "end": None,
        "basis": "منجز (أرشيف الخطّة الموحّدة)",
        "effort": 1,
        "deps": "",
        "criterion": "اسمُ المستخدم الرقمُ الوظيفيّ وكلمةُ مرورٍ مؤقّتةٌ تُلزم بالتغيير عند أوّل دخول لكلّ حساب، "
        "وتصحيحُ رقمٍ وطنيٍّ واحدٍ من مصدر بيانات الموظفين الوزاريّ",
        "note": "طُبّق على الإنتاج والخوادم المحليّة بلا كودٍ ولا PR. الأسماءُ والأرقامُ في لقطة claude.ai لم "
        "تُنقل (المستودعُ عامّ).",
        "gate": "",
        "ref": "جلسة claude/setup-wing-admin-accounts",
        "pr": "",
    },
]


SORT = {"OWN": 233, "DONE": 426}  # بعد OWN-08 (232) وDONE-25 (425)


def _date(value):
    return datetime.date.fromisoformat(value) if value else None


def add_missing(item_model):
    """تُنشئ البنودَ الغائبة؛ تُرجع رموزَ ما أُنشئ."""
    created, offsets = [], {}
    for row in ITEMS:
        offset = offsets[row["src"]] = offsets.get(row["src"], -1) + 1
        if item_model.objects.filter(code=row["code"]).exists():
            continue
        item_model.objects.create(
            code=row["code"],
            src=row["src"],
            lane=row["lane"],
            title=row["title"],
            status=row["status"],
            progress=row["progress"],
            start_date=_date(row["start"]),
            end_date=_date(row["end"]),
            date_basis=row["basis"],
            effort=row["effort"],
            deps=row["deps"],
            criterion=row["criterion"],
            note=row["note"],
            gate=row["gate"],
            ref=row["ref"],
            pr=row["pr"],
            sort_order=SORT[row["src"]] + offset,
        )
        created.append(row["code"])
    return created


def forwards(apps, schema_editor):
    item_model = apps.get_model("roadmap", "RoadmapItem")
    # قاعدةٌ بلا استيراد (اختبار، شجرةٌ جديدة): لا شيء يُزامَن، ولا بنودٌ يتيمة.
    if not item_model.objects.exists():
        return
    add_missing(item_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0009_sync_items_2026_09_24b"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
