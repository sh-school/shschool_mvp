"""مزامنةُ الخارطة الخامسة يومَ 2026-09-24: ما دُمج بعد 0011 ولم يُسجَّل، وقياساتُ المؤشّرات على main@be8be7cc.

حارسةٌ كسابقاتها: لا تلمس بنداً إلّا إن كانت حالتُه وتقدّمُه ما في آخر لقطة؛ والملاحظةُ الموجودة لا تُلحَق ثانيةً؛
والبندُ الجديد يُنشأ إن غاب؛ ولا يُلمس مؤشّرٌ إلّا إن كانت قيمتُه وتاريخُ قياسه ما في آخر لقطة.

- **الجوال:** M-01 يُغلق بـ#544 (K1: 49.4% ← 0.2%، K2: ← 0)؛ وH-04 وH-05 وM-03 بـ#549؛ وM-04 يبدأ (~40، لا يُغلق:
  بقي وسمُ viewport-fit=cover وإصلاحُ بديل الحشوة السفليّة).
- **الهويّة:** LAY-03 يتقدّم (#532 #539 #543) — المرحلتان 1 و2أ وتوحيدُ حدود التوقّف؛ والباقي @container وD2؛ ولا تاريخَ ولا
  بوّابةَ تُلمس. ومؤشّراتُ LK1 وLK2 وLK5 بقياس main@be8be7cc؛ وDBT-36 ملاحظةُ رفع سقف CSS بقرار المالك.
- **الإدارة:** OWN-24 يُغلق بـ#536، وOWN-21 إلى 60 بـ#541 (سلّمُ جلسة الباك إند: 60 الآن، 85 بدمج أهداف اللمس، 100 بعد
  قياس الليليّ)، وOWN-19 ملاحظةُ تكملة أداة الاختيار.
- **عملٌ بلا بند:** N-033 ← #546 (التعويضُ في حصّة زميلٍ بموافقته).
- **ثلاثةُ ديونٍ مفتوحة** فتحتها جلسةُ «اصلاحات 02» وتحقّقتُ منها: DBT-37 (PDPPL: ملفُّ عذر التأخّر بلا clean_photo، الأولويّةُ الأولى)،
  وDBT-38 (id شريط التثبيت مكرَّر)، وDBT-39 (قواعدُ انتقال الصفحات بمحدِّدٍ مقطوع).
- **مؤشّراتُ الجوال MK1 وMK2 وMK7 وMK18** (نصّيّةُ الأساس والهدف) تأخذ أوّلَ قيمةٍ رقميّةٍ حاليّة.

لا تحسم قراراً، ولا تُدرج ما لم يندمج طلبُه (#548 وبنودُ الجدول، #545 #551 #552 #553).
"""

import datetime

from django.db import migrations

STAMP = "[2026-09-24]"
DAY = datetime.date(2026, 9, 24)

# (الرمز، (الحالة، التقدّم) المتوقَّعان، الحالة الجديدة، التقدّم الجديد، طلب الدمج، سطر الملاحظة)
UPDATES = [
    (
        "LAY-03",
        ("todo", 0),
        "doing",
        50,
        "#532 #539 #543",
        "دُمجت ثلاثةُ طلبات: #532 (المرحلة 1: وسمُ {% page_layout %} بثمانية أنماط، وسقّاطةُ الصفحات غير المعلنة، وترحيلُ 20 صفحة، "
        "وحذفُ 12 قاعدةً مكرّرة)، و#539 (المرحلة 2أ: «بلا تمرير» مشروطٌ بسعة النافذة بحدٍّ أدنى 15rem، والقرارُ مضمَّنٌ في "
        "base.html قبل الرسم الأوّل — CLS ≈ 1.0 حين كان مؤجَّلاً في base.js)، و#543 (توحيدُ حدود التوقّف: LK2 من 9 إلى 5). "
        "الباقي: قرارُ @container (ADR-0006) بقياس، وحدُّ اللوحيّ D2، وصفحةُ wings/record.",
    ),
    (
        "M-01",
        ("todo", 0),
        "done",
        100,
        "#544",
        "أُغلق: #544 كتلةٌ واحدة @media (pointer: coarse) ترفع الترويسةَ والفتاتَ وbtn-sm/xs وفرزَ الأعمدة والشاراتِ والمبدِّلاتِ "
        "إلى --control-h والخاناتِ إلى 24px. مقيسٌ بحارس mobile_audit (25 صفحة، خطُّ الأساس الرسميّ): K1 دون 44px: Chromium "
        "49.4% ← 0.2%، وWebKit 49.8% ← 0.2% (هدفُ الخطّة ≤ 25%)؛ K2 دون 24px: 2.6% و3.2% ← 0. بلا تجاوزٍ أفقيّ. والباقي "
        "زرٌّ واحدٌ في record_visit. (أبلغت به جلسةُ «Styleguide».)",
    ),
    (
        "H-04",
        ("todo", 0),
        "done",
        100,
        "#549",
        "أُغلق: #549 رموزُ المنطقة الآمنة --safe-top/--safe-bottom/--safe-inline في :root تقرؤها الترويسةُ والشريطُ اللزجُ "
        "والرسائلُ والتوستُ والشريطُ السفليّ وشريطُ التثبيت؛ حارسُ test_safe_area_tokens. K8 يبقى «لا» (لا viewport-fit بعدُ). "
        "(أبلغت به جلسةُ «اصلاحات 02».)",
    ),
    (
        "H-05",
        ("todo", 0),
        "done",
        100,
        "#549",
        "أُغلق: #549 K18 = 0 — الأربعُ الخامّةُ (9999 و50×2 و20) صارت رموزاً: --z-banner: 300، وثلاثُ قوائمَ إلى --z-dropdown؛ "
        "وصُحّح نصُّ المعيار (المودالُ 9000 < التوست 9500). حارسُ test_z_scale.",
    ),
    (
        "M-03",
        ("todo", 0),
        "done",
        100,
        "#549",
        "أُغلق: #549 قاعدةٌ واحدةٌ لـ.pwa-banner: 80px + --safe-bottom فوق الشريط السفليّ. K7 = لا ساكناً (test_pwa_banner_position) "
        "**ومقيساً** على main@a760f16 (Chromium 375 و390): الفجوةُ +7.5px بلا تداخل — مصدرُها 80px حرفيّةً مقابل شريطٍ ارتفاعُه 72.5px.",
    ),
    (
        "M-04",
        ("todo", 0),
        "doing",
        40,
        "#549",
        "بدأ ولا يُغلق: جُهّزت رموزُ المنطقة الآمنة (#549). الباقي: وسمُ viewport-fit=cover في base.html وبديلُ الحشوة السفليّة، "
        "وتوصيةٌ برمزٍ واحد --dock-h بدل 72/80 الحرفيّتين. وتحقّقٌ على جهازٍ بشقّ.",
    ),
    (
        "OWN-24",
        ("todo", 0),
        "done",
        100,
        "#536",
        "أُغلق: #536 قائمةُ الإدارة ووسومُها وضبطُ اللوحة في core/ (core/admin_menu.py)، وبطاقاتُ dev_cards بقيت في "
        "roadmap/templatetags/admin_monitor.py؛ ونموذجٌ مسجَّلٌ بلا قسم صار تنبيهاً لا فشلاً.",
    ),
    (
        "OWN-21",
        ("doing", 50),
        "doing",
        60,
        "#508 #541",
        "#541: أسماءُ أدوات الإدخال في الإدارة — 620 عنصراً بلا اسم ← 0 على 237 صفحة، وحارسُ axe. مقيسٌ بلا خلل: التباينُ (الوضعان، 375 "
        "و1366، ثماني صفحات)، وترتيبُ التبويب، والتجاوزُ الأفقيّ. **جاهزٌ محلّياً بلا دفع:** أهدافُ اللمس 44px (736 ← 0) — 85% بدمجه. "
        "**لم يُقَس:** الفحصُ الليليّ على 375px — 100% بعده. (سلّمُ جلسة الباك إند.)",
    ),
    (
        "OWN-19",
        ("done", 100),
        "done",
        100,
        "#526 #533 #541",
        "#541 أتمّ تعريبَ أداة الاختيار بين قائمتين (filter_horizontal) في admin_i18n.js — نصوصُها بقيت إنجليزيّةً لأنّ Django 5.2 "
        "غيّرها وكتالوجُه العربيّ على القديمة — وحارسٌ يقارنها بكتالوج Django.",
    ),
    (
        "DBT-36",
        ("todo", 0),
        "todo",
        0,
        "",
        "بقرار المالك 2026-09-24 رُفع سقفُ CSS المشحون 468 ← 470KB (tests/web_vitals.py) بعد أن بلغ M-01 الحجمَ الخامّ 468.1KB بلا هامش، "
        "ثمّ نزل إلى 466.5KB بعد #532. الهامشُ 3.5KB، وأيُّ CSS جديدٍ يأكل منه — فالدَّينُ قائمٌ للتتبّع.",
    ),
]

# بنودٌ جديدة: (الرمز، المسار، العنوان، طلب الدمج، ملاحظة)
NEW_ITEMS = [
    (
        "N-033",
        "backend",
        "التعويضُ في حصّة زميلٍ بموافقته ثمّ اعتماد المنسّق، ووقتُه من جرس طابق الشعبة ويومها",
        "#546",
        "يُغلق به المفتوحُ من N-032 «وقتُ التعويض مع الطابق والخميس». هجرة operations 0058 (حقلان وحالةٌ فقط)، وسُدّت ستُّ ثغراتٍ "
        "كشفتها مراجعةٌ بـ29 وكيلاً (كتابةُ الإشغال فوق التعويض، والاعتمادُ الذاتيّ، والطلبُ العالق، والتواريخ، وطلباتُ المعلّم "
        "المفتوحة، وتنبيهُ الإجازة). نقلت جلسةُ «اصلاحات 01» قرارَ المالك (2026-09-24): الجدولُ المعتمد ممتلئٌ (0 خانة فارغة من "
        "863) فلا حصّةَ فارغةً يُعوَّض فيها، فالتعويضُ في حصّة زميلٍ يدرّس الشعبة بموافقته — منسوبٌ إليها لا قرارٌ مسجَّل. "
        "**يبقى مفتوحاً:** ربطُ Session بحصّتها في الخطّة؛ والجدولُ الأسبوعيّ الديناميكيّ (تصميمُه ينتظر المالك)؛ وغيابُ صاحب التعويض "
        "يومَ تعويضه لا تظهر حصّتُه في صفحة غيابه؛ وexpire_overdue لا يستدعيها شيء.",
    ),
]
NEW_ITEMS_FIRST_ORDER = 465  # بعد N-032 (464)

# ديونٌ فتحتها جلسةُ «اصلاحات 02» أثناء بنود الجوال — **تحقّقتُ من كلٍّ منها في الشيفرة** قبل التسجيل — مفتوحةٌ بلا تاريخ ولا طلب:
# (الرمز، المسار، العنوان، معيار الإغلاق، الملاحظة)
OPEN_DEBTS = [
    (
        "DBT-37",
        "sec",
        "خصوصيّة (PDPPL): تحضيرُ التأخّر يحفظ ملفَّ العذر بلا clean_photo فيبقى EXIF/GPS",
        "كلُّ رفعٍ لملفّ عذرٍ يمرّ بـcore.photo_privacy.clean_photo (يمحو EXIF/GPS ويصغّر — قرار 2026-09-14)، وحارسٌ يمنع حفظَ "
        "ملفٍّ مرفوعٍ بلا تنظيف.",
        "student_affairs/views.py::tardiness_record (نحو :2774-2869) يحفظ excuse_file (PDF/JPG/PNG) في attendance.excuse_file بلا "
        "clean_photo، بينما operations/excuses.py:202 يستعمله. صورةُ عذرٍ من جوّالٍ قد تحمل موقعَ بيتٍ. **الأولويّةُ الأولى بين "
        "الديون الجديدة.** يحتاج طلباً مستقلّاً بمالكٍ وحارس.",
    ),
    (
        "DBT-38",
        "mobile",
        'شريطُ التثبيت: id="pwa-banner" مكرَّر ومنطقُ beforeinstallprompt منسوخ وإغلاقٌ لا يتذكّر في بوّابة وليّ الأمر',
        "id واحدٌ لـpwa-banner في المستند، ومنطقٌ واحدٌ لـbeforeinstallprompt، وإغلاقُه يحفظ pwaDismissed في بوّابة وليّ الأمر أيضاً.",
        "templates/base/base.html:1132 وtemplates/parents/dashboard.html:23 (الثانيةُ تمتدّ من base.html). وقد يكون .pwa-subtitle "
        "معتّماً على العنّابيّ (استكشافٌ **لم يُقَس**).",
    ),
    (
        "DBT-39",
        "frontend",
        "انتقالُ الصفحات: ثلاثُ قواعد في 20-components.css محدِّدُها مقطوعٌ `> {` فتسقط منذ #423 — لا تلاشيَ في أيّ صفحة",
        "قواعدُ الانتقال الثلاثُ بمحدِّدٍ كامل، والتلاشي يعمل في الصفحات، وحارسٌ يمنع محدِّداً مقطوعاً `> {`.",
        "20-components.css (نحو :1349-1358) مثل `#main-content > .exec-dash >  {`. بدأ المالكُ مهمّةً منفصلةً لإصلاحها في جلسةٍ أخرى — "
        "يُربط برقم طلبها حين يُفتح. (المعيارُ الموثَّق في CLAUDE.md «الانتقالُ بين الصفحات»).",
    ),
]
OPEN_DEBTS_FIRST_ORDER = 466  # بعد N-033 (465)

# مؤشّراتٌ رقميّة: (الرمز، (القيمة، تاريخ القياس) المتوقَّعان، القيمة الجديدة، مرجعُ القياس)
# قياسُ اليوم نفسِه يستبدل نقطةَ اليوم في السجلّ لا يضيف نقطةً ثانيةً بالتاريخ ذاته.
KPI_UPDATES = [
    ("LK1", (0.0, DAY), 12.7, "قياس main@be8be7cc: 20 صفحةً من 158"),
    ("LK2", (9.0, DAY), 5.0, "قياس main@be8be7cc: 400 · 640 · 1024 · 1100 · 1440"),
    ("LK5", (998.0, DAY), 990.0, "قياس main@be8be7cc"),
]

# مؤشّراتُ الجوال النصّيّةُ الأساس: قيمتُها الرقميّةُ الحاليّة تُملأ أوّلَ مرّة: (الرمز، القيمة، الوحدة، مرجعُ القياس)
MK_FIRST_READING = [
    (
        "MK1",
        0.2,
        "pct",
        "بعد #544: Chromium 0.2% (431/1) وWebKit 0.2% (434/1) على 25 صفحة (mobile_audit، main@47ed2b07)",
    ),
    (
        "MK2",
        0.0,
        "pct",
        "بعد #544: صفرٌ في Chromium وWebKit على 25 صفحة (mobile_audit، main@47ed2b07)",
    ),
    ("MK7", 0.0, "", "قِيس main@a760f16 (Chromium 375 و390): 0 = لا تداخل، الفجوةُ +7.5px"),
    ("MK18", 0.0, "", "بعد #549: لا قيمةَ خامّاً ≥ 20 (test_z_scale)"),
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
            date_basis="غير مجدول",
            criterion=criterion,
            note=f"{STAMP} فتحتها جلسةُ «اصلاحات 02» أثناء بنود الجوال؛ تحقّقتُ منها في الشيفرة. {extra}",
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
    """تُحدِّث المؤشّراتِ الرقميّةَ التي لم تُمسّ منذ آخر لقطة؛ تُرجع رموزَ ما تغيّر."""
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


def first_readings(kpi_model):
    """تملأ القيمةَ الحاليّةَ لمؤشّرات الجوال النصّيّة إن لم تُقَس قطّ (current وتاريخُ القياس فارغان)."""
    changed = []
    for code, value, unit, source_note in MK_FIRST_READING:
        kpi = kpi_model.objects.filter(
            code=code, current__isnull=True, measured_at__isnull=True
        ).first()
        if kpi is None:
            continue
        _record(kpi, value)
        if unit and not kpi.unit:
            kpi.unit = unit
        if source_note not in kpi.source:
            kpi.source = f"{kpi.source} ({source_note})".strip()
        kpi.save(
            update_fields=["current", "measured_at", "history", "unit", "source", "updated_at"]
        )
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
    kpi_model = apps.get_model("roadmap", "RoadmapKpi")
    sync_kpis(kpi_model)
    first_readings(kpi_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0013_sync_items_2026_09_24d"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
