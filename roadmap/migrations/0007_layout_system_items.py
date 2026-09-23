"""نظامُ أنماط التخطيط المركزيّة: بنودُه ومؤشّراتُه وقرارُه، وربطُه ببنود سطح المكتب القائمة.

يُدرَج هنا لا كخطّةٍ رابعة: U-33 مظلّتُه، وVI-24 يبقى بندَ الموجات (ترحيلِ الصفحات)،
وVI-23 يبقى قياسَ الأساس المُصيَّر، وVI-29 يبقى المركزيّة. الجديدُ سبعةُ بنودٍ برمز `LAY-`
(لا يتصادم مع ترقيم `U-` الذي تملكه جلسةُ الخارطة) وخمسةُ مؤشّراتٍ `LK1..LK5` وقرارٌ `D-16`.

حارسةٌ كـ0003..0006: كلُّ إنشاءٍ يتخطّى ما وُجد بالرمز، والبنودُ القائمة تُلحَق بها
ملاحظةُ ربطٍ وحدها (لا حالةَ ولا تاريخَ — موعدُ بندٍ قائمٍ قرارٌ للمالك)، ولا تُلحَق ثانيةً.

**كلُّ التواريخ والجهد والأهداف مقترَحةٌ لم يعتمدها المالك** (قاعدةُ الخارطة)، ومنها قرارُ D-16
الذي يبقى «مفتوحاً» حتى يحسمه. قياسُ الأساس من `scripts/measure_layout_kpis.py` على main
(ecf674bf، آخرُ نشرٍ ناجحٍ f2dea3b8) يوم 2026-09-23.
"""

import datetime

from django.db import migrations

STAMP = "[2026-09-23]"
DAY = datetime.date(2026, 9, 23)
BASIS = "مقترَح — لم يعتمده المالك"
D = datetime.date

# (الرمز، المسار، العنوان، البداية، النهاية، الجهد، الاعتماديّات، معيار الإغلاق، البوّابة)
NEW_ITEMS = [
    (
        "LAY-01",
        "frontend",
        "قرار D-16: اعتماد كتالوج أنماط التخطيط السبعة (لوحة، مدخل وحدة، سجل، تفصيل، نموذج،"
        " ورقة كثيفة، تقرير) ومعايير قبولها",
        D(2026, 9, 28),
        D(2026, 10, 2),
        1,
        "جرد القوالب (157 صفحة) وقياس LK1..LK5",
        "قرارٌ مكتوب من المالك على D-16: الأنماط السبعة أو تعديلُها، وحدودُ القبول (axe، لقطات"
        " الأجهزة الأربعة، CLS/INP، سقف CSS 240KB).",
        "owner",
    ),
    (
        "LAY-02",
        "frontend",
        "مواصفات الأنماط السبعة وصفحة الدليل: لكل نمطٍ حالاتُه الأربع (تحميل، فارغة، خطأ، ممتلئة)"
        " وسلوكُه على الأجهزة الأربعة",
        D(2026, 10, 5),
        D(2026, 10, 16),
        4,
        "LAY-01، VI-13",
        "صفحةُ الدليل تعرض الأنماط السبعة بلا مخالفة axe خطيرة وبلقطاتٍ نهاراً/ليلاً على الأجهزة"
        " الأربعة؛ والمعيارُ الموسَّع موثَّقٌ في CLAUDE.md (يوسِّع معيار عرض النافذة ولا يلغيه).",
        "",
    ),
    (
        "LAY-03",
        "frontend",
        "أساسُ التخطيط: طبقةٌ واحدة، وتوحيدُ نقاط التوقف (9 اليوم)، واستعلاماتُ الحاويات، ودمجُ"
        " تعريفَي .exec-dash، ووسمُ {% page_layout %} وحارسٌ يرفض صفحةً بلا نمط",
        D(2026, 10, 19),
        D(2026, 11, 6),
        6,
        "LAY-02، VI-29، VI-13",
        "LK1 يبدأ بالصعود وحارسٌ يمنع صفحةً جديدة بلا نمط؛ LK2 ≤ 5؛ تعريفٌ واحدٌ لـ.exec-dash؛"
        " وصافي حجم CSS المصغَّر ≤ 0 (لا يتجاوز 240KB) — يُقابَل بحذف CSS المحلّي.",
        "",
    ),
    (
        "LAY-04",
        "frontend",
        "سجلُّ الودجات وإعدادُ الأدوار: قالبٌ واحد للّوحات بإعدادٍ لكل دور (ودجات وترتيب وحجم)،"
        " مقيَّدٌ بالقدرة (RBAC)",
        D(2026, 11, 2),
        D(2026, 11, 20),
        6,
        "LAY-03",
        "LK4 = 1؛ اختبارٌ يثبت أنّ ودجةً لا يراها من لا قدرةَ له عليها؛ لقطاتُ المقارنة لكلّ دورٍ"
        " بلا فرقٍ غير معتمَد؛ ولا CSS جديدٌ لدورٍ جديد.",
        "",
    ),
    (
        "LAY-05",
        "frontend",
        "النموذجُ التجريبيّ: لوحةُ المدير وصفحةُ سجلّ ونموذجٌ بالأنماط الجديدة على الإنتاج،"
        " مع قياسٍ قبل/بعد",
        D(2026, 11, 16),
        D(2026, 11, 30),
        4,
        "LAY-03، LAY-04، VI-23",
        "D1/D2 وCLS قبل/بعد مسجَّلةٌ في الخارطة؛ الصفحاتُ الثلاث مدموجةٌ ومنشورةٌ بعد الدوام"
        " (CODE-VERIFIED ≠ PRODUCTION-PROVEN) وعاملُ الخدمة بإصدارٍ مرقَّمٍ جديد.",
        "",
    ),
    (
        "LAY-06",
        "frontend",
        "حالاتُ الودجة والقوائم: فارغةٌ بمكوّنٍ مركزيّ (تنكمش ولا تحتلّ بطاقةً كاملة)، وهياكلُ"
        " تحميلٍ تحجز ارتفاعها، وخطأٌ بإعادة محاولة",
        D(2026, 11, 9),
        D(2026, 12, 4),
        5,
        "LAY-02",
        "LK3 = 100% (كان 24.3%)؛ CLS < 0.1 على الصفحات الثلاث؛ حارسٌ يمنع جدولاً بلا حالة فارغة.",
        "",
    ),
    (
        "LAY-07",
        "desktop",
        "اختباراتُ قابليّة الاستخدام حسب الدور: 3–5 مستخدمين لكلّ دورٍ رئيسيّ (مدير، مشرف جناح،"
        " معلّم) بمهمّةٍ معياريّة",
        D(2026, 12, 1),
        D(2026, 12, 17),
        3,
        "LAY-05",
        "زمنُ الإنجاز ونسبةُ النجاح مسجَّلان لكلّ دور؛ والنتائجُ تُغذّي أولويّةَ موجات VI-24.",
        "owner",
    ),
]

# (الرمز، المسار، الاسم، الأساس، الهدف، الاتّجاه، الوحدة)
NEW_KPIS = [
    ("LK1", "frontend", "صفحاتٌ تعلن نمطَ تخطيطها", 0, 100, "up", "pct"),
    ("LK2", "frontend", "حدودُ التوقّف المختلفة في CSS (المتجاورةُ حدٌّ واحد)", 9, 5, "down", "حدّ"),
    ("LK3", "frontend", "تغطيةُ الحالة الفارغة في الصفحات ذات الجدول", 24.3, 100, "up", "pct"),
    ("LK4", "frontend", "قوالبُ لوحات الأدوار", 11, 1, "down", "قالب"),
    ("LK5", "frontend", "أسطرُ CSS محلّيٍّ مربوطٍ بقوالب الصفحات", 1088, 300, "down", "سطر"),
]
KPI_SOURCE = "scripts/measure_layout_kpis.py على main (ecf674bf) — تحليلٌ نصّيٌّ لا قياسٌ مُصيَّر"
KPI_BASIS = "الهدفُ مقترَحٌ لم يعتمده المالك؛ يُحسَم مع D-16"

DECISION = (
    "D-16",
    "اعتمادُ كتالوج أنماط التخطيط المركزيّة: سبعةُ أنماط (لوحة، مدخل وحدة، سجل، تفصيل، نموذج،"
    " ورقة كثيفة، تقرير) ومعايير قبولها",
    "المالك",
    "2026-10-02",
    "LAY-02..LAY-07 (وموجاتُ VI-24)",
    "3 أنماط (لوحة/قائمة/نموذج) — 7 أنماط — 20 نمطاً.",
    "7 أنماط: أقلُّ من ذلك يدمج ما يختلف عرضُه وتمريرُه (ورقةٌ كثيفة مع سجل)، وأكثرُ يعيد التشتّت."
    " قاعدةُ الفصل: النمطان يختلفان إن اختلف عرضُ المحتوى أو سلوكُ التمرير.",
)

# (الرمز، سطرُ الملاحظة) — ملاحظاتُ ربطٍ فقط: موعدُ بندٍ قائمٍ قرارٌ للمالك لا لمزامنة.
NOTES = [
    (
        "U-33",
        "مظلّةُ نظام أنماط التخطيط المركزيّة: LAY-01..LAY-07 ومؤشّرات LK1..LK5 وقرار D-16."
        " يبقى هذا البندُ للقياس النهائيّ (D1/D2) ومعيار الإغلاق الشامل.",
    ),
    (
        "VI-23",
        "الجزءُ الساكن مُنجَزٌ: جردُ القوالب على main (157 صفحة، 11 قالبَ دور) وسكربتُ"
        " scripts/measure_layout_kpis.py. الباقي القياسُ المُصيَّر ويحتاج جلسةَ دخول المطوّر.",
    ),
    (
        "VI-24",
        "تُنفَّذ الموجات عبر نظام التخطيط (LAY-01..LAY-07) لا صفحةً بصفحة، بعد نموذجه التجريبيّ"
        " LAY-05؛ ترتيبُها حسب الوحدة (الجودة 20 صفحة، شؤون الموظفين 14، شؤون الطلاب 14، الجدول 12)."
        " موعدُه الحاليّ يسبق LAY-05 — تعديلُه قرارٌ للمالك.",
    ),
    (
        "VI-29",
        "تقتسم مع LAY-03 حارسَ الطبقة الواحدة؛ لا يُكرَّر: LAY-03 يضيف وسمَ النمط وتوحيدَ نقاط التوقف.",
    ),
]


def _next_order(item_model):
    top = item_model.objects.order_by("-sort_order").values_list("sort_order", flat=True).first()
    return (top or 0) + 1


def add_items(item_model):
    """تُنشئ بنودَ LAY الغائبة؛ تُرجع رموزَ ما أُنشئ."""
    created = []
    order = _next_order(item_model)
    for code, lane, title, start, end, effort, deps, criterion, gate in NEW_ITEMS:
        if item_model.objects.filter(code=code).exists():
            continue
        item_model.objects.create(
            code=code,
            src="LAY",
            lane=lane,
            title=title,
            status="todo",
            progress=0,
            start_date=start,
            end_date=end,
            date_basis=BASIS,
            effort=effort,
            deps=deps,
            criterion=criterion,
            note=f"{STAMP} أُضيف مع نظام أنماط التخطيط؛ تحت المظلّة U-33 (قرار D-16).",
            gate=gate,
            ref="U-33 · VI-24 · VI-29",
            sort_order=order,
        )
        order += 1
        created.append(code)
    return created


def add_kpis(kpi_model):
    """تُنشئ مؤشّراتِ LK الغائبة؛ تُرجع رموزَ ما أُنشئ."""
    created = []
    order = (
        kpi_model.objects.order_by("-sort_order").values_list("sort_order", flat=True).first() or 0
    ) + 1
    for code, lane, name, base, target, direction, unit in NEW_KPIS:
        if kpi_model.objects.filter(code=code).exists():
            continue
        kpi_model.objects.create(
            code=code,
            lane=lane,
            name=name,
            baseline=base,
            current=base,
            target=target,
            direction=direction,
            unit=unit,
            source=KPI_SOURCE,
            measured_at=DAY,
            history=[],
            extra={"basis": KPI_BASIS, "track": "desktop+mobile"},
            sort_order=order,
        )
        order += 1
        created.append(code)
    return created


def add_decision(decision_model):
    """تُنشئ القرارَ D-16 مفتوحاً إن غاب؛ تُرجع رموزَ ما أُنشئ."""
    code, title, decider, due, blocks, options, recommendation = DECISION
    if decision_model.objects.filter(code=code).exists():
        return []
    order = (
        decision_model.objects.order_by("-sort_order").values_list("sort_order", flat=True).first()
        or 0
    ) + 1
    decision_model.objects.create(
        code=code,
        src="LAY",
        title=title,
        status="open",
        decider=decider,
        due=due,
        blocks=blocks,
        options=options,
        recommendation=recommendation,
        sort_order=order,
    )
    return [code]


def annotate(item_model):
    """تُلحِق ملاحظاتِ الربط على البنود القائمة مرّةً واحدة؛ لا تمسّ حالةً ولا تاريخاً."""
    changed = []
    for code, line in NOTES:
        item = item_model.objects.filter(code=code).first()
        if item is None or line in item.note:
            continue
        item.note = f"{item.note}\n{STAMP} {line}".strip()
        item.save(update_fields=["note", "updated_at"])
        changed.append(code)
    return changed


def forwards(apps, schema_editor):
    item_model = apps.get_model("roadmap", "RoadmapItem")
    # قاعدةٌ بلا استيراد (اختبار، شجرةٌ جديدة): لا بنودَ يتيمةٌ بلا خارطتها.
    if not item_model.objects.exists():
        return
    add_items(item_model)
    add_kpis(apps.get_model("roadmap", "RoadmapKpi"))
    add_decision(apps.get_model("roadmap", "RoadmapDecision"))
    annotate(item_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0006_sync_items_2026_09_23c"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
