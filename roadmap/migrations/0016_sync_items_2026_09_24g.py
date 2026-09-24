"""مزامنةُ الخارطة السابعة يومَ 2026-09-24: اعتمادُ الجدول الجديد وقياسُ مؤشّراته، و#555، وأربعةَ عشرَ ديناً مفتوحاً.

حارسةٌ كسابقاتها: لا تلمس بنداً إلّا إن كانت حالتُه وتقدّمُه ما في آخر لقطة؛ والملاحظةُ الموجودة لا تُلحَق ثانيةً؛
والبندُ الجديد يُنشأ إن غاب؛ ولا يُلمس مؤشّرٌ إلّا إن كانت قيمتُه وتاريخُ قياسه ما في آخر لقطة.

- **الجدول الجديد اعتُمد في الإنتاج** (التوليد c2dba53a، أُنشئ 18:33Z واعتُمد قبل 21:47 الدوحة) — والقياسُ **قراءةً فقط من
  الإنتاج** أجرته جلسةُ الجدولة: SK1 12 ← **7** (HC5: 4، HC16B: 3، وHC6 = 0)، SK2 98.2 ← 99.3، SK3 17.9% ← **6.1%** (الهدفُ ≤ 10
  محقَّق)، SK4 26% ← 22.8% (≤ 15 لم يُبلَغ — SCH-11 لاحقاً)، SK5 0 ← **2** (الهدفُ ≥ 2 محقَّق). وSCH-08 يبقى 90: لم يُولَّد يومٌ
  مستقبليٌّ بعد، فحصصُ الأحد تُولَّد أوّلَ طلب.
- **N-035 ← #555** (أيقونةُ حوار التأكيد المكسورة)، و**N-036 ← #563** (رقمُ الحصّة محفوظٌ في Session).
- **أربعةَ عشرَ ديناً مفتوحاً** (DBT-40..53): أربعةٌ لمداخل الرفع بلا clean_photo (تحقّقتُ منها) من جلسة «اصلاحات 02»، وثمانيةٌ
  من جلسة «Styleguide» (بطلب المالك «كلها»؛ تقديراتُها مقترحةٌ ولم أتحقّق منها كلَّها)، وثلاثةٌ من جلسة الأيقونة وما وجدتُه
  (تحقّقتُ من تكرار صفّي الوثيقة، ومن iconSvg، ومن عدد شبكات Docker)، وواحدٌ من جلسة «اصلاحات 01» (حجمُ operations/models.py).

لا تحسم قراراً، ولا تُغلق DBT-37 (ينتظر #560).
"""

import datetime

from django.db import migrations

STAMP = "[2026-09-24]"
DAY = datetime.date(2026, 9, 24)
BASIS = "غير مجدول"

# (الرمز، (الحالة، التقدّم) المتوقَّعان، الحالة الجديدة، التقدّم الجديد، طلب الدمج، سطر الملاحظة) — ملاحظاتُ تقدّمٍ بلا تغيير حالة
UPDATES = [
    (
        "SCH-08",
        ("doing", 90),
        "doing",
        90,
        "",
        "اعتمد المالكُ الجدولَ الجديدَ في الإنتاج: التوليد c2dba53a (أُنشئ 2026-09-24 18:33Z، اعتُمد قبل 21:47 الدوحة). لم يُولَّد يومٌ "
        "مستقبليٌّ بعد (الجلساتُ مولَّدةٌ ليوم الخميس 24/9 وحده)، فحصصُ الأحد 27/9 تُولَّد أوّلَ طلبٍ من الجدول الجديد نفسه — "
        "تتحقّق منها جلسةُ الجدولة بعد أن يُفتح الأحدُ ثمّ يُغلق البند.",
    ),
    (
        "SCH-11",
        ("todo", 0),
        "todo",
        0,
        "",
        "بعد اعتماد الجدول الجديد: SK4 (الرياضيّاتُ في السادسة والسابعة) = 22.8% والهدفُ ≤ 15% لم يُبلَغ — هذا البندُ هو الذي يُبلغه.",
    ),
    (
        "DBT-36",
        ("todo", 0),
        "todo",
        0,
        "",
        "بعد #555: CSS الخامّ 464,743 بايتاً من سقف 470KB (هامشٌ نحو 5.3KB).",
    ),
    (
        "Q-11",
        ("todo", 0),
        "todo",
        0,
        "",
        "من جلسة «Styleguide»: لا حارسَ للشكل — القياسُ بالأهداف لا يرى تغيّرَ الشكل (قرصُ التحذير الأبيض صار 44px بدل 24px ولم يكشفه "
        "K1؛ كشفته مراجعةٌ يدويّة)، وأُضيف اختبارٌ لموضعٍ واحدٍ فقط.",
    ),
    (
        "VI-13",
        ("todo", 0),
        "todo",
        0,
        "",
        "من جلسة «Styleguide»: المقارنةُ البصريّة لبقيّة الصفحات غيرُ موجودة؛ والقياسُ بالأهداف لا يرى تغيّرَ الشكل (انظر Q-11).",
    ),
]

# بنودٌ جديدةٌ لعملٍ دُمج بلا بند: (الرمز، المسار، العنوان، طلب الدمج، ملاحظة)
NEW_ITEMS = [
    (
        "N-035",
        "frontend",
        "أيقونةُ عنوان حوار التأكيد (data-confirm) كانت مكسورةً — base.js يكتب #icon-alert-triangle من ورقةٍ محذوفة",
        "#555",
        "37 استعمالاً في 25 قالباً. صارت الأيقونةُ من قاموس core/icons.py (status_warning) عبر data-icon-sprite. الحارسُ الجديد "
        "js_icon_problems في tests/test_icon_dictionary.py يمسح static/js وكلَّ <app>/static وقوالبَ PWA (سقط على base.js قبل "
        "الإصلاح ومرّ بعده) — فالمؤشّرُ «مراجعُ أيقوناتٍ مكسورةٌ في السكربتات = 0» (كان 1) محروسٌ بحارسٍ ثابتٍ لا سقّاطة، فلا مؤشّرَ "
        "جديد. التباينُ 5.74 نهاراً و7.71 ليلاً، والCSS الخامّ 464,743 بايتاً، وحُوِّل style= المضمَّن في JS (مرّتين) إلى صنفَين مركزيَّين. "
        "(أبلغت به جلسةُ إصلاح الأيقونة؛ وهي بقيّةُ حذف الورقة في DONE-05.)",
    ),
    (
        "N-036",
        "backend",
        "رقمُ الحصّة محفوظٌ في Session (period_number) بدل استنتاجه من الوقت، وفلترُ «الحصّة» في «حصصي اليوم» يقرؤه",
        "#563",
        "هجرة operations 0059، وتعبئةُ القائم. يُغلق به المفتوحُ «ربطُ Session بحصّتها في الخطّة» الذي دُوّن بعد #531. وهو أساسٌ لبند "
        "الجدول الأسبوعيّ الديناميكيّ (يبقى مفتوحاً، تصميمُه ينتظر المالك). (أبلغت به جلسةُ «اصلاحات 01».)",
    ),
]
NEW_ITEMS_FIRST_ORDER = 470  # بعد N-034 (469)

# ديونٌ مفتوحةٌ بلا تاريخ ولا طلب: (الرمز، المسار، العنوان، معيار الإغلاق، الملاحظة)
OPEN_DEBTS = [
    (
        "DBT-40",
        "sec",
        "خصوصيّة (PDPPL): مرفقُ إجازة الموظّف يُحفظ بلا clean_photo — قد يكون تقريراً طبّيّاً",
        "يمرّ بـcore.photo_privacy.clean_photo، ويخرج من KNOWN_UNCLEANED في tests/test_uploads_are_photo_cleaned.py.",
        "staff_affairs/views.py::leave_request_create — **الأشدُّ حساسيّةً بين المداخل الستّة، يلي #560 (DBT-37)**. تحقّقتُ أنّه يقرأ FILES "
        "بلا clean_photo، وأنّ clean_photo لا يُستعمل في الإنتاج إلا في operations/excuses.py:202.",
    ),
    (
        "DBT-41",
        "sec",
        "خصوصيّة (PDPPL): مرفقُ استثناء الحضور للموظّف يُحفظ بلا clean_photo",
        "يمرّ بـclean_photo ويخرج من KNOWN_UNCLEANED.",
        "staff_affairs/views_attendance.py::my_permits. تحقّقتُ أنّه يقرأ FILES بلا clean_photo. (أبلغت به جلسةُ «اصلاحات 02».)",
    ),
    (
        "DBT-42",
        "sec",
        "خصوصيّة (PDPPL): مرفقُ النشاط الطلّابيّ يُحفظ بلا clean_photo — صورٌ فيها طلبة",
        "يمرّ بـclean_photo في الإضافة والتعديل معاً، ويخرج من KNOWN_UNCLEANED.",
        "student_affairs/views.py::activity_add و::activity_edit. تحقّقتُ أنّهما يقرآن FILES بلا clean_photo.",
    ),
    (
        "DBT-43",
        "sec",
        "خصوصيّة (PDPPL): دليلُ الإجراء في الجودة يُحفظ بلا clean_photo",
        "تُراجَع: هل يقبل صورةً؟ وهل هو بياناتٌ شخصيّة؟ ثمّ يمرّ بـclean_photo أو يُوثَّق سببُ إعفائه.",
        "quality/views.py::upload_evidence و::_process_task_update. تحقّقتُ أنّهما يقرآن FILES بلا clean_photo، **ولم أتحقّق أنّهما "
        "يقبلان صوراً** — الأخفُّ بين المداخل الستّة.",
    ),
    (
        "DBT-44",
        "desktop",
        "سطحُ المكتب بلا حارسٍ لأهداف اللمس والفأرة: 49 هدفاً من 491 دون 24px (≈10%)",
        "حارسٌ لسطح المكتب (K2 على desktop) بسقّاطةٍ لا تزيد، ثمّ خفضٌ إلى 0 وفق قرار D1 (24px للفأرة).",
        "خطُّ الأساس (chromium/desktop) يسجّل 49 من 491؛ لكنّ GUARDED في tests/mobile_audit.py يحرس الجوّالَ وحدَه، فيزيد العددُ ولا "
        "يسقط شيء. M-01 لم يمسّه لأنّه coarse فقط. (من جلسة «Styleguide»؛ لم أتحقّق.)",
    ),
    (
        "DBT-45",
        "mobile",
        "آخرُ هدفٍ دون 44px على الجوّال (K1 = 0.2%): خانةُ clinic-check «أُرسل إلى البيت»",
        "K1 = 0: تُقاس التسميةُ المحيطة هدفاً للمس، أو يُرفع صندوقُ الخانة.",
        "clinic/record_visit — رُفعت إلى 24px لأنّ التسميةَ حولها هي منطقةُ اللمس الأوسع، لكنّ mobile_audit يقيس صندوقَ العنصر نفسِه "
        "فيعدّها على Chromium وWebKit. (من جلسة «Styleguide»؛ لم أتحقّق.)",
    ),
    (
        "DBT-46",
        "desktop",
        "تزاحمُ عناوين أعمدة سجلّ الموظفين على الألواح (641–1000px)",
        "عناوينُ الأعمدة مقروءةٌ بلا اقتطاعٍ ولا تداخلٍ على 641–1000px.",
        "أعمدةٌ بعرض 6–8% أضيقُ من عناوينها؛ قديمٌ قبل M-01 بمقياسٍ مقارَب (أثبته مراجعٌ مستقلّ). (من جلسة «Styleguide»؛ لم أتحقّق.)",
    ),
    (
        "DBT-47",
        "frontend",
        "تعريفُ نقاط التوقّف (LK2) مكرَّرٌ في scripts/measure_layout_kpis.py وcore/styleguide.py",
        "تعريفٌ واحدٌ يقرؤه الاثنان، لا اختبارٌ يربط نسختين.",
        "يربطهما اختبارٌ وحده؛ يتّصل بـLAY-03. (من جلسة «Styleguide»؛ لم أتحقّق.)",
    ),
    (
        "DBT-48",
        "ops",
        "أدواتُ جلسات العمل: حاوياتُها بلا متصفّحاتِ Playwright، وحرّاسُ design_ratchet وa11y_ratchet تأخذ نحو 16 و14 دقيقةً محلّياً",
        "متصفّحاتُ Playwright في صورة الجلسة، وحرّاسُ السقّاطات تعمل بدقائقَ لا بعشراتها، أو تُفصل عن تشغيل الحرّاس المعتاد.",
        "WebKit لا يُشتقّ محلّياً فأرقامُ الجوال تُؤخذ من سجلّ CI وتُطبَّق بسكربت (سقط الحارسُ عمداً مرّتين)؛ وتشغيلُ السقّاطتين معاً "
        "علّق 27 دقيقة (من جلسة «Styleguide»). **وقِستُ اليومَ ما يوافقه**: حزمةُ حرّاس CSS من 119 اختباراً أخذت 27 دقيقة محلّياً.",
    ),
    (
        "DBT-49",
        "frontend",
        "ترقيمُ أقسام دليل الهويّة يدويّ (22 قسماً)، وكلماتٌ في نصّه مثل «shadow» تولّد صنفاً في Tailwind",
        "ترقيمٌ يُشتقّ من ترتيب الأقسام، وحارسٌ يمنع كلماتِ نصٍّ تولّد أصنافَ Tailwind بلا قصد.",
        "كلُّ قسمٍ جديدٍ يستلزم إعادةَ ترقيمٍ بسكربت؛ والكلماتُ تُلزم إعادةَ بناء tailwind.min.css (حدث في #519). (من جلسة «Styleguide»؛ "
        "لم أتحقّق.)",
    ),
    (
        "DBT-50",
        "frontend",
        "app.js فيه دالّةٌ iconSvg قريبةٌ من warningIcon في base.js",
        "دالّةٌ واحدةٌ تولّد أيقونة السكربتات من قاموس core/icons.py.",
        "static/js/app.js:59 وstatic/js/base.js:671 — تحقّقتُ من وجودهما. (أبلغت به جلسةُ إصلاح الأيقونة.)",
    ),
    (
        "DBT-51",
        "quality",
        "docs/governance/regression_guards.md فيه صفّان مكرّران: «حجمُ CSS المصغَّر» و«Core Web Vitals والحمولة» بسقفَين مختلفَين",
        "صفٌّ واحدٌ لكلّ حارس، وسقفُ CSS الخامّ 470KB وحدَه.",
        "الأسطر 47–50 على main: «CSS خامٌ ≤ 468KB» و«≤ 470KB» في الصفّين المكرَّرين — تحقّقتُ منهما. (أبلغت به جلسةُ إصلاح الأيقونة.)",
    ),
    (
        "DBT-52",
        "ops",
        "شبكاتُ Docker: شبكاتُ schoolos-*_default فارغةٌ من جلساتٍ متوقّفة أنهكت نطاقاتِ العناوين فتعذّر تشغيلُ خادمِ جلسةٍ جديد",
        "سكربتُ تنظيفٍ للجلسات المتوقّفة (بإذن المالك قبل أيّ حذف)، ولا تعذُّر في تشغيل جلسةٍ جديدة.",
        "أبلغته جلسةُ إصلاح الأيقونة (14 شبكةً)؛ عدّدتُ **10** الآن على هذا الجهاز.",
    ),
    (
        "DBT-53",
        "backend",
        "operations/models.py بلغ حدَّ حارس الحجم بالضبط (2243 سطراً) — كلُّ حقلٍ بعده يستلزم تقسيمَ الملفّ",
        "تقسيمُ operations/models.py إلى حزمةٍ حسب المسؤوليّة (كما staff_affairs/attendance/) بلا تغيير سلوك، ويُعرض على المالك.",
        "خطُّ الأساس 2218 والحدُّ +25 = 2243، وطولُ الملفّ على main الآن 2243 — تحقّقتُ. لا حلَّ له في #563 (أبلغته جلسةُ «اصلاحات 01» "
        "لتعرضه على المالك).",
    ),
]
OPEN_DEBTS_FIRST_ORDER = 472  # بعد N-036 (471)

# مؤشّراتٌ رقميّة: (الرمز، (القيمة، تاريخ القياس) المتوقَّعان، القيمة الجديدة، مرجعُ القياس) — قياسُ الإنتاج قراءةً فقط بعد اعتماد
# التوليد c2dba53a؛ ونقطةُ اليوم في السجلّ تُستبدل لا تتكرّر (والأساسُ باقٍ في baseline).
KPI_UPDATES = [
    ("SK1", (12.0, DAY), 7.0, "الإنتاج بعد اعتماد c2dba53a: HC5 4 وHC16B 3 وHC6 0"),
    (
        "SK2",
        (98.2, DAY),
        99.3,
        "الإنتاج بعد اعتماد c2dba53a (pattern_match): HC6 بلا مخالفة؛ الفرقُ عن 100 من نمط المزدوجات لا من القسمة",
    ),
    ("SK3", (17.9, DAY), 6.1, "الإنتاج بعد اعتماد c2dba53a — الهدفُ ≤ 10 محقَّق"),
    ("SK4", (26.0, DAY), 22.8, "الإنتاج بعد اعتماد c2dba53a — الهدفُ ≤ 15 لم يُبلَغ"),
    (
        "SK5",
        (0.0, DAY),
        2.0,
        "الإنتاج: 7d775ba4 (5 مخالفات) و5253da63 القديم (67) — الهدفُ ≥ 2 محقَّق",
    ),
]


def sync(item_model):
    """تُطبِّق تحديثاتِ البنود الحارسة؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, expected, status, progress, pr, line in UPDATES:
        item = item_model.objects.filter(code=code).first()
        if item is None or (item.status, item.progress) != expected or line in item.note:
            continue
        item.status, item.progress = status, progress
        if pr:
            item.pr = pr
        item.note = f"{item.note}\n{STAMP} {line}".strip()
        item.save(update_fields=["status", "progress", "pr", "note", "updated_at"])
        changed.append(code)
    return changed


def add_missing(item_model):
    """تُنشئ بنودَ العمل المدموج الغائبة؛ تُرجع رموزَ ما أُنشئ."""
    created = []
    for offset, (code, lane, title, pr, extra) in enumerate(NEW_ITEMS):
        if item_model.objects.filter(code=code).exists():
            continue
        note = f"{STAMP} عملٌ دُمج بلا بندٍ في الخارطة، سُجّل مُغلقاً برقم طلبه."
        item_model.objects.create(
            code=code,
            src="NEW",
            lane=lane,
            title=title,
            status="done",
            progress=100,
            start_date=DAY,
            end_date=DAY,
            date_basis="محدَّث يدوياً",
            pr=pr,
            note=f"{note} {extra}".strip(),
            sort_order=NEW_ITEMS_FIRST_ORDER + offset,
        )
        created.append(code)
    return created


def add_open_debts(item_model):
    """تُنشئ الديونَ المفتوحةَ الغائبة بلا تاريخٍ ولا طلب؛ تُرجع رموزَ ما أُنشئ."""
    created = []
    for offset, (code, lane, title, criterion, extra) in enumerate(OPEN_DEBTS):
        if item_model.objects.filter(code=code).exists():
            continue
        item_model.objects.create(
            code=code,
            src="DBT",
            lane=lane,
            title=title,
            status="todo",
            progress=0,
            date_basis=BASIS,
            criterion=criterion,
            note=f"{STAMP} {extra}",
            sort_order=OPEN_DEBTS_FIRST_ORDER + offset,
        )
        created.append(code)
    return created


def _record(kpi, value):
    """تكتب قياسَ اليوم في السجلّ: تستبدل نقطةَ اليوم إن وُجدت، وإلّا تُلحقها."""
    today = DAY.isoformat()
    history = [point for point in (kpi.history or []) if point.get("d") != today]
    history.append({"d": today, "v": value})
    kpi.current, kpi.measured_at, kpi.history = value, DAY, history


def sync_kpis(kpi_model):
    """تُحدِّث المؤشّرات التي لم تُمسّ منذ آخر لقطة؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, expected, value, source_note in KPI_UPDATES:
        kpi = kpi_model.objects.filter(code=code).first()
        if kpi is None or (kpi.current, kpi.measured_at) != expected:
            continue
        _record(kpi, value)
        if source_note not in kpi.source:
            kpi.source = f"{kpi.source} ({source_note})".strip()
        kpi.save(update_fields=["current", "measured_at", "history", "source", "updated_at"])
        changed.append(code)
    return changed


def forwards(apps, schema_editor):
    item_model = apps.get_model("roadmap", "RoadmapItem")
    # قاعدةٌ بلا استيراد (اختبار، شجرةٌ جديدة): لا شيء يُزامَن، ولا بنودٌ يتيمة.
    if not item_model.objects.exists():
        return
    sync(item_model)
    add_missing(item_model)
    add_open_debts(item_model)
    sync_kpis(apps.get_model("roadmap", "RoadmapKpi"))


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0015_sync_items_2026_09_24f"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
