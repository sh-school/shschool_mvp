"""قاموسُ أيقونات SchoolOS — الأيقونةُ تُختار بالمعنى، والرسمُ تابعٌ له.

كانت القوالبُ تطلب الأيقونةَ باسم شكلها (`list-checks`، `bar-chart`)، فحمل الشكلُ
الواحدُ معانيَ لا صلةَ بينها: `list-checks` كان «مركز معلومات الطلبة» و«رصد
الغياب» و«الإسناد» و«الجودة» في قائمةٍ واحدة. والقاموسُ يقلب الاتّجاه: الصفحةُ
تطلب **المعنى** (`absence`)، وهذا الملفُّ وحده يقرّر رسمَه:

    {% load icons %}
    {% icon "absence" %}
    {% icon "behavior_violation" degree=3 label="مخالفة من الدرجة الثالثة" %}

والرسمُ أحدُ ثلاثة:

* ``hi:<name>`` رمزٌ من Hugeicons Free كما هو (MIT — ``core/icon_sources/``).
* ``cmp:<base>+<badge>`` كيانٌ وشارةُ حالةٍ في الزاوية نفسها دائماً — يُركَّب
  آليّاً، فلا يُرسم «طالبٌ غائب» باليد.
* ``local:<name>`` ما لا تملكه المكتبة أو تملكه بحرفٍ لاتينيّ — مرسومٌ على شبكتها
  وسُمكها في ``core/icon_sprite.py``، وسقفُه ``MAX_LOCAL``.

و``mirror=True`` لرسمٍ يدلّ على اتّجاه (سهمٌ، زمنٌ يسري): يُعرَّف باتّجاه LTR
ويُعكس في الواجهة العربيّة.

وورقةُ الرموز ``static/icons/sprite.svg`` تُولَّد من هذا الملفّ ولا تُحرَّر:

    python manage.py build_icon_sprite

والحارسُ في ``tests/test_icon_dictionary.py`` يُسقط البناءَ إن اختلفت الورقةُ عن
مولّدها، أو تشارك معنيان رسماً واحداً، أو دخل حرفٌ لاتينيٌّ رسماً.
"""

from __future__ import annotations

from dataclasses import dataclass

#: أقصى الرسوم المحلّيّة — ما زاد يُطلب من المكتبة أو يُعاد النظرُ فيه.
MAX_LOCAL = 12

GROUPS = {
    "module": "وحدات المنصّة",
    "school": "الحياة المدرسيّة",
    "entity": "الكيانات",
    "data": "البيانات والتقارير",
    "action": "الأفعال",
    "status": "الحالات والتنبيهات",
    "chrome": "هيكل الواجهة",
}

#: شاراتُ الحالة — تُركَّب على الكيان أسفلَ نهاية السطر (اليسار في العربيّة).
BADGES = {
    "present": "حاضر",
    "absent": "غائب",
    "late": "متأخّر",
    "leave": "مستأذن / خرج",
    "clinic": "في العيادة",
    "swap": "بديل",
    "alert": "يحتاج متابعة",
    "add": "إضافة",
}

#: درجاتُ المخالفة السلوكيّة في اللائحة — أسنانُ الرسم بعددها.
VIOLATION_DEGREES = (1, 2, 3, 4)


@dataclass(frozen=True)
class Icon:
    label: str
    group: str
    glyph: str
    mirror: bool = False

    @property
    def kind(self) -> str:
        return self.glyph.split(":", 1)[0]

    @property
    def source(self) -> str:
        return self.glyph.split(":", 1)[1]


ICONS: dict[str, Icon] = {
    # ── وحدات المنصّة ──
    "quality": Icon("الجودة والخطّة التشغيليّة", "module", "hi:task-done-01"),
    "behavior": Icon("السلوك", "module", "hi:balance-scale"),
    "dashboard": Icon("لوحة التحكّم", "module", "hi:dashboard-square-01"),
    "library": Icon("المكتبة", "module", "hi:books-01"),
    "grades": Icon("الدرجات وكشوفها", "module", "local:gradebook-ar"),
    "notifications": Icon("الإشعارات", "module", "hi:notification-01"),
    "transport": Icon("النقل المدرسيّ", "module", "hi:school-bus"),
    "observation": Icon("الزيارات الصفّيّة", "module", "hi:teaching"),
    "assessments": Icon("التقييمات والاختبارات", "module", "hi:quiz-02"),
    "clinic": Icon("العيادة المدرسيّة", "module", "hi:stethoscope-02"),
    "staff": Icon("شؤون الموظفين", "module", "hi:id-card-lanyard"),
    "student_info": Icon("مركز معلومات الطلبة", "module", "hi:student-card"),
    "wings": Icon("أجنحة المدرسة", "module", "local:wing"),
    "security": Icon("الأمان والصلاحيات", "module", "hi:security-lock"),
    "workload": Icon("الإسناد والأنصبة", "module", "hi:assignments"),
    "activities": Icon("الأنشطة", "module", "hi:champion"),
    "periods_today": Icon("حصص اليوم (حيّة)", "module", "local:period-live"),
    "schedule": Icon("الجدول الدراسي", "module", "hi:time-schedule"),
    "academic": Icon("الشؤون الأكاديميّة والموادّ", "module", "hi:book-open-01"),
    "parents": Icon("أولياء الأمور", "module", "hi:user-love-01"),
    "breach": Icon("خرق البيانات (PDPPL)", "module", "hi:security-warning"),
    "messages": Icon("الرسائل والبريد", "module", "hi:mail-01"),
    "counseling": Icon("الإرشاد الاجتماعيّ والنفسيّ", "module", "hi:mentoring"),
    "developer": Icon("المساعد والمطوّر", "module", "hi:robot-01"),
    "exam_control": Icon("الكنترول", "module", "hi:file-locked"),
    "services": Icon("الخدمات المدرسيّة", "module", "hi:customer-service-01"),
    # بنودُ القوائم الفرعيّة: كانت ستّةُ بنودٍ في قائمة «الجودة» برسمٍ واحد
    "my_actions": Icon("إجراءاتي", "module", "hi:task-edit-01"),
    "plan_execution": Icon("تنفيذ الخطّة", "module", "hi:rocket-01"),
    "self_review": Icon("المراجعة الذاتيّة", "module", "hi:search-list-01"),
    "plan_committee": Icon("لجنة منفّذي الخطّة", "module", "hi:user-group-03"),
    "review_committee": Icon("لجنة المراجعة الذاتيّة", "module", "hi:user-multiple-02"),
    "staff_register": Icon("سجلّ الموظفين", "module", "hi:user-list"),
    "departments": Icon("الأقسام التعليميّة", "module", "hi:hierarchy-square-01"),
    "exam_analytics": Icon("تحليلات الاختبارات", "module", "hi:chart-evaluation"),
    "observation_reports": Icon("تقارير الأداء الصفّيّ", "module", "hi:presentation-bar-chart-01"),
    "elearning": Icon("التعليم الإلكترونيّ", "module", "hi:online-learning-01"),
    "mail_unread": Icon("الرسائل الجديدة", "module", "hi:inbox-unread"),
    "mail_sent": Icon("الرسائل المرسلة", "module", "hi:mail-send-01"),
    "password": Icon("كلمة المرور", "module", "hi:lock-password"),
    "two_factor": Icon("المصادقة الثنائيّة", "module", "hi:two-factor-access"),
    # ── الحياة المدرسيّة ──
    "psychology": Icon("الأخصائي النفسيّ", "school", "hi:brain-02"),
    "behavior_team": Icon("فريق سلوك الطلبة", "school", "hi:user-shield-01"),
    "wing_coverage": Icon("تغطية الأجنحة والإنابة", "school", "hi:user-arrow-left-right"),
    "absence": Icon("الغياب", "school", "cmp:student+absent"),
    "behavior_violation": Icon("مخالفة سلوكيّة (بالدرجة)", "school", "local:violation-degree"),
    "attendance_register": Icon("رصد الحضور", "school", "cmp:student+present"),
    "swap_requests": Icon(
        "طلبات التبديل والتنقّلات", "school", "hi:arrow-data-transfer-horizontal", mirror=True
    ),
    "behavior_committee": Icon("لجنة الضبط والقرار", "school", "hi:court-law"),
    "leave": Icon("الإجازات", "school", "hi:beach"),
    "tardiness": Icon("التأخّر", "school", "cmp:student+late"),
    "attendance_teacher_absence": Icon("غياب المعلّمين والبدلاء", "school", "cmp:teacher+absent"),
    "compensation": Icon("الحصص التعويضيّة", "school", "hi:calendar-add-01"),
    "staff_evaluation": Icon("تقييم أداء الموظفين", "school", "hi:star-award-01"),
    "failing_students": Icon("الطلاب المتعثّرون والراسبون", "school", "cmp:student+alert"),
    "licences": Icon("الرخص المهنيّة", "school", "hi:license"),
    "bells": Icon("التوقيت والأجراس", "school", "hi:school-bell-01"),
    "clinic_visit": Icon("زيارة الطالب للعيادة", "school", "cmp:student+clinic"),
    "exemptions": Icon("تفريغات المعلّمين", "school", "hi:calendar-block-01"),
    "sent_home": Icon("استئذان وإرسال للمنزل", "school", "cmp:student+leave"),
    "substitution": Icon("تعيين بديل", "school", "cmp:teacher+swap"),
    "arabic_subject": Icon("اللغة العربيّة", "school", "local:dad-letter"),
    "certificates": Icon("الشهادات", "school", "hi:certificate-01"),
    "islamic_ed": Icon("التربية الإسلاميّة", "school", "hi:quran-01"),
    "prayer": Icon("الصلاة والمصلّى", "school", "hi:mosque-02"),
    "qr_door": Icon("رمز باب الشعبة", "school", "hi:qr-code"),
    # ── الكيانات ──
    "students": Icon("الطلاب والشُّعب", "entity", "hi:students"),
    "profile": Icon("الملفّ الشخصيّ", "entity", "hi:user"),
    "children": Icon("أبنائي (بوّابة الوليّ)", "entity", "hi:child"),
    "school_building": Icon("المدرسة", "entity", "hi:school"),
    "teacher": Icon("المعلّم", "entity", "hi:teacher"),
    "student": Icon("الطالب", "entity", "hi:student"),
    # ── البيانات والتقارير ──
    "location": Icon("الموقع والخريطة", "data", "hi:maps-location-01"),
    "stats": Icon("الإحصائيّات والتوزيعات", "data", "hi:chart-column"),
    "checklist": Icon("قائمة بنود", "data", "hi:check-list"),
    "document": Icon("مستند", "data", "hi:file-01"),
    "reports": Icon("التقارير", "data", "hi:analytics-01"),
    "date": Icon("التاريخ والتقويم", "data", "hi:calendar-03"),
    "kpi": Icon("مؤشّرات الأداء", "data", "hi:target-02"),
    "trend": Icon("الاتّجاه عبر الزمن", "data", "hi:chart-line-data-01", mirror=True),
    "folder": Icon("مجلّد", "data", "hi:folder-open"),
    "policy": Icon("اللوائح والقرارات الرسميّة", "data", "hi:legal-document-01"),
    # ── الأفعال ──
    "edit_record": Icon("تحرير سجلّ / ملاحظة", "action", "hi:note-edit"),
    "print": Icon("طباعة", "action", "hi:printer"),
    "confirm": Icon("تأكيد", "action", "hi:tick-02"),
    "export_excel": Icon("تصدير Excel", "action", "hi:file-export"),
    "export_pdf": Icon("تصدير PDF", "action", "hi:file-download"),
    "refresh": Icon("تحديث / إعادة", "action", "hi:reload"),
    "add": Icon("إضافة", "action", "hi:add-01"),
    "search": Icon("بحث", "action", "hi:search-01"),
    "import": Icon("استيراد", "action", "hi:file-import"),
    "call_parent": Icon("استدعاء وليّ الأمر", "action", "hi:call-02"),
    "save": Icon("حفظ", "action", "hi:floppy-disk"),
    "delete": Icon("حذف", "action", "hi:delete-02"),
    "generate": Icon("توليد تلقائيّ", "action", "hi:magic-wand-01"),
    "link": Icon("الربط", "action", "hi:link-01"),
    "student_add": Icon("إضافة طالب", "action", "cmp:student+add"),
    "download": Icon("تنزيل", "action", "hi:download-04"),
    "all_present": Icon("الكلّ حاضر", "action", "hi:tick-double-02"),
    "filter": Icon("تصفية", "action", "hi:filter-horizontal"),
    "upload": Icon("رفع", "action", "hi:upload-04"),
    "edit": Icon("تعديل", "action", "hi:pencil-edit-02"),
    "user_add": Icon("إضافة مستخدم", "action", "hi:user-add-01"),
    "view": Icon("عرض", "action", "hi:view"),
    "attach": Icon("مرفق", "action", "hi:attachment-01"),
    "calculate": Icon("حساب", "action", "hi:calculator-01"),
    "user_remove": Icon("إزالة مستخدم", "action", "hi:user-remove-01"),
    # ── الحالات والتنبيهات ──
    "status_warning": Icon("تحذير", "status", "hi:alert-02"),
    "status_success": Icon("نجاح / مكتمل", "status", "hi:checkmark-circle-02"),
    "status_error": Icon("خطأ / مرفوض", "status", "hi:cancel-circle"),
    "time": Icon("الوقت والمهلة", "status", "hi:clock-01"),
    "status_info": Icon("معلومة", "status", "hi:information-circle"),
    "empty": Icon("لا بيانات", "status", "hi:inbox"),
    "loading": Icon("جارٍ التحميل", "status", "hi:loading-03"),
    "status_critical": Icon("حرِج / عاجل", "status", "hi:alert-diamond"),
    "offline": Icon("لا اتّصال", "status", "hi:wifi-disconnected-01"),
    "status_blocked": Icon("محظور / غير متاح", "status", "hi:unavailable"),
    "tip": Icon("تلميح", "status", "hi:bulb"),
    # ── هيكل الواجهة ──
    "settings": Icon("الإعدادات", "chrome", "hi:settings-01"),
    "back": Icon("رجوع", "chrome", "hi:arrow-left-02", mirror=True),
    "close": Icon("إغلاق", "chrome", "hi:cancel-01"),
    "maintenance": Icon("صيانة وأدوات", "chrome", "hi:wrench-01"),
    "next": Icon("التالي", "chrome", "hi:arrow-right-01", mirror=True),
    "prev": Icon("السابق", "chrome", "hi:arrow-left-01", mirror=True),
    "theme_dark": Icon("الوضع الليليّ", "chrome", "hi:moon-02"),
    "install_app": Icon("تثبيت التطبيق", "chrome", "hi:smart-phone-01"),
    "logout": Icon("تسجيل الخروج", "chrome", "hi:logout-03", mirror=True),
    "menu": Icon("القائمة", "chrome", "hi:menu-01"),
    "role_switch": Icon("تبديل الدور", "chrome", "hi:user-switch"),
    "theme_light": Icon("الوضع النهاريّ", "chrome", "hi:sun-03"),
}


def get(key: str) -> Icon:
    try:
        return ICONS[key]
    except KeyError:
        raise KeyError(f"لا أيقونةَ بالمعنى {key!r} في core/icons.py") from None


#: معانٍ لها رسمٌ مفصَّلٌ في الأحجام الكبيرة — وفي القوائم يُزدحم فيُبسَّط.
#: الجناحُ نجمةٌ ثمانيّة في 16–24 بكسل، ومبنًى داخلها في 32 و48.
DETAILED_AT = {"wings": ("xl", "2xl")}


def symbol_id(key: str, degree: int | None = None, size: str = "") -> str:
    """معرّفُ الرمز في الورقة — ``i-<key>``، ولدرجة المخالفة ``i-violation-degree-<n>``،
    وللرسم المفصَّل في الحجم الكبير ``i-<key>-lg``."""
    if degree is not None:
        return f"i-violation-degree-{degree}"
    if size and size in DETAILED_AT.get(key, ()):
        return f"i-{key}-lg"
    return f"i-{key}"
