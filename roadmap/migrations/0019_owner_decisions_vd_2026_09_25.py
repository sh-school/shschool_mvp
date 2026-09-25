"""قراراتُ المالك على VD1..VD8 (2026-09-25) وبندُ «الإدارة نهاريّةٌ افتراضيّاً».

أجاب المالكُ على قرارات خطّة إصلاح الهويّة في محادثة جلسة 8104، ثمّ **أكّد لجلسة الخارطة مباشرةً** ما يأتي:

- **VD2 محسوم:** «الوضعُ النهاريّ افتراضيّ للجميع» — يبقى قرارُ 2026-09-19 ويُعمَّم على الإدارة (كانت تقرأ
  prefers-color-scheme والمنصّةُ لا). فيسقط الشطرُ الثاني من VI-37 (قراءةُ تفضيل النظام) ويبقى الأوّل
  (theme-color وforced-colors وprefers-contrast).
- **VD1 وVD5 وVD6 وVD7 وVD8 محسومة قراراً** بتفويضه 8104 في «الباقي توصيك»، وأكّد لجلسة الخارطة: «محسومة قرارا ولكن
  يجب العمل عليها». فالحسمُ قرارٌ لا تنفيذ: البنودُ التي تحجبها تبقى مفتوحةً ولا يتغيّر موعدُ أيٍّ منها.
- **VD3 محسوم** (أجاب في محادثة 8104 ثمّ أكّده لجلسة الخارطة): «لا هويتنا خاصة بمدارسنا» و«كلا لا تراسل أحداً — هذا جهدنا الشخصي
  أنا سفيان المطوّر، والتنسيق في كل هذا مع مدير المدرسة» — فلا مراسلةَ لـGCO ولا للوزارة ولا لأحد، ومطابقةُ GBA اتّساقٌ لا التزام.
- **VD4 لا يُحسم:** أعاد المالكُ نطاقَه بعد جوابه على «الباقي» (توصيتُه السابقة «SVG ومعكوسٌ رسميّان» لم تعد تنطبق)، فيبقى
  **مقترَحاً معدَّلاً مفتوحاً** بانتظار تأكيده المباشر. وD-14 وD-15 مفتوحان.
- **بندٌ جديدٌ مقترَحٌ مفتوح** VI-54 «الإدارة نهاريّةٌ افتراضيّاً كالمنصّة» — بلا تاريخٍ ولا حالةٍ منجزة، وبوّابتُه المالك؛
  وتنتظر 8104 إذنَه قبل التنفيذ.

وبعد دفع 0018 اندمج طلبان يُسجَّلان هنا:

- **#571** (8096) ملاحظةٌ على OWN-19: هجرة core/0072 (بياناتٌ فقط، لا رجوع) — **مدموجٌ لا منشور**، ولا يُنشر إلا بتأكيدٍ صريحٍ من
  المالك لجلسة النشر بعد اطّلاعه على الرقم 16 (إسناداتٌ مباشرةٌ لمستخدمين تُحذف بالتتالي).
- **#577** (8061) الطلبُ الأوّلُ من ثلاثةٍ للجدول الأسبوعيّ الديناميكيّ: **N-041 قيد التنفيذ 1/3** (عدُّ طلباتٍ لا جهد). وD-21 يبقى
  مفتوحاً للنقاش بطلب المالك.

حارسةٌ كسابقاتها: تحسم القرارَ المفتوحَ وحدَه، ولا تُلحق ملاحظةً موجودة، ولا تلمس حالةَ بندٍ ولا تاريخَه.
"""

import datetime

from django.db import migrations

STAMP = "[2026-09-25]"
DAY = datetime.date(2026, 9, 25)
REF = "memory/on_demand/project_identity_remediation_plan_2026_09_24.md"
ITEM_BASIS = "غير مجدول — اقترحته جلسة 8104 وسجّله المالك مقترَحاً مفتوحاً"

_DELEGATED = (
    "حسمها المالكُ قراراً في 2026-09-25: فوّض جلسةَ 8104 بتوصيتها («الباقي توصيك») ثمّ أكّد لجلسة الخارطة: "
    "«محسومة قرارا ولكن يجب العمل عليها». **الحسمُ قرارٌ لا تنفيذ** — البندُ الذي يحجبه يبقى مفتوحاً وموعدُه لم يُغيَّر."
)

# (الرمز، الحالة المتوقَّعة، الحالة الجديدة، سطرُ الحسم)
DECISIONS = [
    (
        "VD1",
        "open",
        "decided",
        f"{_DELEGATED} النصُّ: 150ms خروجاً و250ms ظهوراً ثمّ View Transitions (زمنٌ ≤ 400ms، V-K37).",
    ),
    (
        "VD2",
        "open",
        "decided",
        "حسمه المالكُ وأكّده لجلسة الخارطة مباشرةً (2026-09-25): «الوضعُ النهاريّ افتراضيّ للجميع» — يبقى قرارُ 2026-09-19 ويُعمَّم على "
        "الإدارة (كانت تقرأ prefers-color-scheme والمنصّةُ لا). **فيسقط الشطرُ الثاني من VI-37** (قراءةُ تفضيل النظام) ويبقى الأوّل. "
        "ويترتّب عليه VI-54 (مقترَحٌ مفتوح): الإدارةُ نهاريّةٌ افتراضيّاً كالمنصّة.",
    ),
    (
        "VD3",
        "open",
        "decided",
        "حسمه المالكُ (2026-09-25) في محادثة جلسة 8104 وأكّده لجلسة الخارطة مباشرةً: «لا هويتنا خاصة بمدارسنا» (لا دليلَ هويّةٍ "
        "وزاريّاً للمدارس)، و«كلا لا تراسل أحداً — هذا جهدنا الشخصي أنا سفيان المطوّر، والتنسيق في كل هذا مع مدير المدرسة». "
        "**فلا مراسلةَ لـGCO ولا للوزارة ولا لأحد**، ورملُ القائمة يبقى على مسؤوليّته. ومطابقةُ GBA اتّساقٌ لا التزام: يبقى VI-38 وVI-39 "
        "لعمى الألوان والتناغم.",
    ),
    (
        "VD5",
        "open",
        "decided",
        f"{_DELEGATED} النصُّ: الثانويّاتُ الرسميّة (GBA) مع ترميزٍ مزدوج (ΔE2000 ≥ 10 تحت الديوتان والبروتان).",
    ),
    (
        "VD6",
        "open",
        "decided",
        f"{_DELEGATED} النصُّ: «SchoolOS» صيغةً وحيدةً لاسم المنتج بلا رقم إصدارٍ في الواجهة (الموجودُ اليوم بحسب 8104: SchoolOS "
        "وSchoolOS v5.1 وv5.2 وSchoolOS-SAMM ونظام SchoolOS، والمانيفستُ العامّ يضع اسمَ المدرسة اسماً للتطبيق).",
    ),
    (
        "VD7",
        "open",
        "decided",
        f"{_DELEGATED} النصُّ: المكوّناتُ (VI-42/43/46) قبل LAY-05.",
    ),
    (
        "VD8",
        "open",
        "decided",
        f"{_DELEGATED} النصُّ: لا رفعَ ثانياً لسقف CSS الخامّ بعد 470KB. **D-14 وD-15 لم يُحسما** (لم يعدّهما 8104 ضمن «الباقي») "
        "فتوصيتاهما لم تُحدَّثا بعد.",
    ),
]

# قراراتٌ تبقى مفتوحةً وتُلحَق بها ملاحظة: (الرمز، سطر الملاحظة)
OPEN_NOTES = [
    (
        "VD4",
        "**يُعاد نطاقُه — مقترَحٌ معدَّل مفتوح، لم يُحسم (2026-09-25):** بعد جواب المالك على VD3 لم تعد التوصيةُ السابقة «SVG ومعكوسٌ "
        "رسميّان» تنطبق (بنقل 8104). الصيغةُ المقترَحة المعدَّلة: ملفّاتُ شعار المدرسة الأصليّة (SVG أو عالية الدقّة) من مدير "
        "المدرسة، والنسخةُ المعكوسة ومساحةُ الحماية نصنعهما بلا فلتر تبييض؛ ويُقرأ V-K39 «نسخُ الشعار الأصليّة». **وافق المالكُ "
        "على إخراجه من المحسوم وتسجيلِه مقترَحاً معدَّلاً مفتوحاً بانتظار تأكيده المباشر.**",
    ),
]

# (الرمز، (الحالة، التقدّم) المتوقَّعان، رمزُ الطلب يُضاف، سطر الملاحظة) — طلباتٌ دُمجت بعد دفع 0018
UPDATES = [
    (
        "OWN-19",
        ("done", 100),
        "#571",
        "#571 حذفُ ثمانِ صلاحيّاتٍ يتيمةٍ لنموذجَين حُذفا (StaffEvaluation في #436 وTeacherSubjectQualification بقرار 2026-09-05)، "
        "وقرارُ حذف اليتيمة للمالك 2026-09-24: هجرةُ core/0072 **بياناتٌ فقط ولا رجوع لها** (بلا تغيير مخطّط)، تحذف ما نوعُ محتواه أحدُ "
        "النموذجَين بالاسم وبشرط أن يبقى غيرَ موجود، وتسجّل في سجلّ النشر ما تحذفه من إسناداتٍ (معرّف ← اسم الصلاحيّة) فيُستعاد يدويّاً. "
        "**قياسُ الإنتاج قبل النشر (جلسة النشر، قراءةٌ فقط، 2026-09-25):** 8 صلاحيّاتٍ يتيمةٍ، و**16 إسناداً مباشراً لمستخدمين** يُحذف "
        "بالتتالي، و0 لمجموعات (600 ← 592). حارسُه tests/test_delete_orphan_permissions_migration.py (7 حالات). **مدموجٌ لا منشور:** "
        "لا يُنشر إلا بتأكيدٍ صريحٍ من المالك لجلسة النشر بعد اطّلاعه على الرقم 16.",
    ),
]

# ملاحظاتٌ على بنودٍ قائمةٍ بلا حالةٍ ولا تاريخ: (الرمز، (الحالة، التقدّم) المتوقَّعان، سطر الملاحظة)
NOTES = [
    (
        "VI-36",
        ("todo", 0),
        "حُسم VD1 (2026-09-25): 150ms خروجاً و250ms ظهوراً ثمّ View Transitions (زمنٌ ≤ 400ms، V-K37) — قرارٌ لا تنفيذ؛ والمدّةُ "
        "اليومَ 500ms خروجاً وظهوراً (--transition-page).",
    ),
    (
        "VI-37",
        ("todo", 0),
        "حُسم VD2 (2026-09-25): «الوضعُ النهاريّ افتراضيّ للجميع» فيسقط الشطرُ الثاني (قراءةُ تفضيل النظام) ويبقى الشطرُ الأوّل "
        "(theme-color وforced-colors وprefers-contrast). لم يُغيَّر موعدُه ولا جهدُه — قرارُ المالك في تعديلهما. وتنفيذُ «الإدارة "
        "نهاريّةٌ افتراضيّاً» بندٌ مستقلّ VI-54.",
    ),
    (
        "VI-11",
        ("todo", 0),
        "VD4 يُعاد نطاقُه (2026-09-25) — **مقترَحٌ معدَّل مفتوحٌ لا محسوم**: ملفّاتُ شعار المدرسة الأصليّة (SVG أو عالية الدقّة) من "
        "مدير المدرسة، والنسخةُ المعكوسة ومساحةُ الحماية نصنعهما بلا فلتر تبييض (بنقل 8104)؛ فلا يُعتمد ما كُتب هنا من «SVG ومعكوسٌ "
        "رسميّان» قبل تأكيد المالك المباشر.",
    ),
    (
        "VI-38",
        ("todo", 0),
        "حُسم VD5 (2026-09-25): الثانويّاتُ الرسميّة (GBA) مع ترميزٍ مزدوج (ΔE2000 ≥ 10) — قرارٌ لا تنفيذ. وبحسم VD3 صارت مطابقةُ "
        "GBA اتّساقاً لا التزاماً (لا مراسلةَ لأحد)؛ فيبقى هذا البندُ لعمى الألوان والتناغم.",
    ),
    (
        "VI-39",
        ("todo", 0),
        "حُسم VD3 (2026-09-25): لا مراسلةَ لأحد، ومطابقةُ GBA اتّساقٌ لا التزام — فيبقى هذا البندُ لعمى الألوان والتناغم.",
    ),
    (
        "VI-53",
        ("todo", 0),
        "حُسم VD6 (2026-09-25): «SchoolOS» صيغةً وحيدةً لاسم المنتج بلا رقم إصدارٍ في الواجهة — قرارٌ لا تنفيذ، وبوّابتُه «المالك» "
        "لم تُرفع.",
    ),
    (
        "LAY-05",
        ("todo", 0),
        "حُسم VD7 (2026-09-25): المكوّناتُ (VI-42/43/46) قبل LAY-05 — قرارٌ لا تنفيذ. **لم يُغيَّر موعدُه**: إزاحتُه إلى 11-22 ← 12-06 "
        "مقترَحةٌ في خطّة الهويّة ولم يعتمدها المالكُ بعد.",
    ),
    (
        "DBT-36",
        ("todo", 0),
        "حُسم VD8 (2026-09-25): لا رفعَ ثانياً لسقف CSS الخامّ بعد 470KB — فأيُّ CSS قادمٍ يُقابَل بخفضٍ لا برفع السقف.",
    ),
]

# بندٌ مقترَحٌ جديد (بلا تاريخٍ ولا حالةٍ منجزة): (الرمز، المسار، العنوان، الجهد، الاعتماديّات، معيار الإغلاق، ملاحظة)
NEW_ITEMS = [
    (
        "VI-54",
        "frontend",
        "الإدارة نهاريّةٌ افتراضيّاً كالمنصّة (بعد حسم VD2)",
        0.5,
        "VD2",
        "لا كتلةَ @media (prefers-color-scheme: dark) في admin_theme.css؛ وdata-theme غير المضبوط أو auto = نهاريّ؛ والليليُّ باختيار "
        "المستخدم وحدَه؛ وحارسٌ في test_admin_theme.",
        "اقترحته جلسة 8104 (2026-09-25) بعد حسم VD2: حذفُ كتلة @media (prefers-color-scheme: dark) من admin_theme.css وجعلُ "
        "data-theme غير المضبوط/auto = نهاريّاً، والليليُّ باختيار المستخدم وحده. **سجّله المالكُ بنداً مقترَحاً مفتوحاً** (بلا تاريخٍ "
        "ولا تنفيذ)؛ وتنتظر 8104 إذنَه قبل التنفيذ. الجهدُ تقديرُها (نحو 0.5 يوم).",
    ),
]
NEW_ITEMS_FIRST_ORDER = 659  # بعد VI-53 (658)

# عملٌ جارٍ اندمج أوّلُ طلباته: (الرمز، المسار، العنوان، التقدّم، طلبُ الدمج، معيار الإغلاق، ملاحظة)
IN_PROGRESS_ITEMS = [
    (
        "N-041",
        "backend",
        "الجدولُ الأسبوعيّ الديناميكيّ: أسبوعٌ فعليّ من حصص الأيّام (ثلاثةُ طلبات)",
        33,
        "#577",
        "ثلاثةُ طلبات: القارئ (#577 مدموج) ← أزرارُ التنقّل بين الأسابيع ← الطباعةُ وPDF وExcel للأسبوع الفعليّ. ولا يُنشر ما يجعل "
        "صفحةَ الجدول تقرأ من Session قبل تحقّق صباح الأحد 2026-09-27 من مطابقة جلسات اليوم للجدول المعتمد (قيدٌ اتّفقت عليه 8061 و8033).",
        "**قيد التنفيذ 1/3 بتقدير 8061 (عدُّ طلباتٍ لا جهد؛ لا يُغلق).** #577 (جلسة «اصلاحات 01» 8061، اندمج main@5b4d3a0e، "
        "2026-09-25 05:42 الدوحة): قارئُ أسبوعٍ فعليّ من حصص الأيّام بلا واجهة — operations/services/schedule_week.py::week_lessons "
        "(Session حيثُ وُلّد اليومُ، وScheduleSlot حيثُ لم يُولَّد بوسم «وفق الخطّة»، ويومُ إجازة الطلبة بسببه بلا خانة)، وغلافُ LessonCell "
        "بـkind (تبديل/إشغال/تعويض) وoriginal_teacher، والحاملُ صاحبُ الحصّة اليوم؛ وScheduleService.get_week_schedule وget_week_matrix؛ "
        "**قراءةٌ محضة لا تكتب**، واستعلاماتٌ ثابتةُ العدد. حصصٌ سبقت #563 بلا رقم يُشتقّ رقمُها من جرس شعبتها وما لا يُشتقّ يُعدّ في "
        "unplaced. لا قالبَ ولا مسارَ ولا زرَّ تنقّل (الطلب 2) ولا تعديلَ على الطباعة وPDF وExcel (الطلب 3). التحقّق: 18 اختباراً جديداً "
        "في tests/test_week_schedule.py و60 خضراء مع صفحات الجدول القائمة؛ ruff 0.4.4 وRadon وmypy بإصدار CI. **دُمج ونشرُه بيد "
        "جلسة النشر (لم يُؤكَّد بعد)، ولا واجهةَ فيه فلا يقرأ صفحةَ الجدول من Session.** القرارُ D-21 مفتوحٌ للنقاش بطلب المالك: "
        "موافقتُه بلفظه («نعم أوافق على التوصيات الأربع») نقلتها 8061 من جلستها ولم يؤكّدها لجلسة الخارطة.",
    ),
]
IN_PROGRESS_FIRST_ORDER = 492  # بعد DBT-55 (491)


def decide(decision_model):
    """تحسم القراراتِ المفتوحة وحدها وتُلحق نصَّ الحسم بالتوصية؛ تُرجع رموزَ ما حُسم."""
    decided = []
    for code, expected, status, line in DECISIONS:
        decision = decision_model.objects.filter(code=code, status=expected).first()
        if decision is None:
            continue
        decision.status, decision.decision_date = status, DAY
        if line not in decision.recommendation:
            decision.recommendation = f"{decision.recommendation}\n{STAMP} {line}".strip()
        decision.save(update_fields=["status", "decision_date", "recommendation", "updated_at"])
        decided.append(code)
    return decided


def annotate_open(decision_model):
    """تُلحق ملاحظةً بقرارٍ يبقى مفتوحاً مرّةً واحدة بلا حسمه؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, line in OPEN_NOTES:
        decision = decision_model.objects.filter(code=code, status="open").first()
        if decision is None or line in decision.recommendation:
            continue
        decision.recommendation = f"{decision.recommendation}\n{STAMP} {line}".strip()
        decision.save(update_fields=["recommendation", "updated_at"])
        changed.append(code)
    return changed


def sync_notes(item_model):
    """تُلحق ملاحظاتِ الحسم بالبنود القائمة (لا حالةَ ولا تاريخ) مرّةً واحدة؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, expected, line in NOTES:
        item = item_model.objects.filter(code=code).first()
        if item is None or (item.status, item.progress) != expected or line in item.note:
            continue
        item.note = f"{item.note}\n{STAMP} {line}".strip()
        item.save(update_fields=["note", "updated_at"])
        changed.append(code)
    return changed


def sync(item_model):
    """تُطبِّق تحديثاتِ البنود الحارسة (ملاحظةٌ ورمزُ طلبٍ يُضاف)؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, expected, pr, line in UPDATES:
        item = item_model.objects.filter(code=code).first()
        if item is None or (item.status, item.progress) != expected or line in item.note:
            continue
        item.pr = " ".join(dict.fromkeys([*item.pr.split(), *pr.split()]))
        item.note = f"{item.note}\n{STAMP} {line}".strip()
        item.save(update_fields=["pr", "note", "updated_at"])
        changed.append(code)
    return changed


def add_in_progress(item_model):
    """تُنشئ بنودَ العمل الجاري الغائبة قيدَ التنفيذ؛ تُرجع رموزَ ما أُنشئ."""
    created = []
    for offset, (code, lane, title, progress, pr, criterion, note) in enumerate(IN_PROGRESS_ITEMS):
        if item_model.objects.filter(code=code).exists():
            continue
        item_model.objects.create(
            code=code,
            src="NEW",
            lane=lane,
            title=title,
            status="doing",
            progress=progress,
            start_date=DAY,
            date_basis="محدَّث يدوياً",
            pr=pr,
            criterion=criterion,
            note=f"{STAMP} عملٌ دُمج أوّلُ طلباته بلا بندٍ في الخارطة، سُجّل قيدَ التنفيذ. {note}",
            sort_order=IN_PROGRESS_FIRST_ORDER + offset,
        )
        created.append(code)
    return created


def add_items(item_model):
    """تُنشئ البنودَ المقترَحةَ الغائبة مفتوحةً بلا تاريخ؛ تُرجع رموزَ ما أُنشئ."""
    created = []
    for offset, (code, lane, title, effort, deps, criterion, note) in enumerate(NEW_ITEMS):
        if item_model.objects.filter(code=code).exists():
            continue
        item_model.objects.create(
            code=code,
            src="VI",
            lane=lane,
            title=title,
            status="todo",
            progress=0,
            date_basis=ITEM_BASIS,
            effort=effort,
            deps=deps,
            criterion=criterion,
            note=f"{STAMP} {note}",
            gate="owner",
            ref=REF,
            sort_order=NEW_ITEMS_FIRST_ORDER + offset,
        )
        created.append(code)
    return created


def forwards(apps, schema_editor):
    item_model = apps.get_model("roadmap", "RoadmapItem")
    # قاعدةٌ بلا استيراد (اختبار، شجرةٌ جديدة): لا شيء يُزامَن، ولا بنودٌ يتيمة.
    if not item_model.objects.exists():
        return
    decision_model = apps.get_model("roadmap", "RoadmapDecision")
    decide(decision_model)
    annotate_open(decision_model)
    sync(item_model)
    sync_notes(item_model)
    add_in_progress(item_model)
    add_items(item_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0018_sync_items_2026_09_25"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
