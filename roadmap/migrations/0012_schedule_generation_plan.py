"""خطّةُ إصلاح توليد الجدول: بنودُها ومؤشّراتُها وقرارُها (قرارُ المالك 2026-09-24 بإدراجها).

سببُها تدقيقُ الجدول الحيّ يومَ 2026-09-24: الجدولُ المعتمد فيه 12 مخالفةً صلبة (HC6) دخلت برخصة الكثافة
ملاذاً أخيراً بلا سدادٍ ولا بوّابة، والجدولُ الجديد يُعمل به الأحدَ 2026-09-27. المرجعُ
`docs/schedule_generation_remediation_plan_2026-09.md` (تدفعه جلسةُ الجدولة مع أوّل طلب).

- **SCH-01..SCH-16** (برمزٍ مستقلّ لا يتصادم مع `U-` ولا `N-`): 01..08 عاجلةٌ قبل الأحد، و09..12 المرحلةُ الأولى
  (أسبوعان)، و13..16 المرحلةُ الثانية (شهر، يلزمها ADR).
- **D-17** مفتوح: رخصةُ الكثافة ملاذٌ أخيرٌ أم تُمنع — للمالك وحده، ولا تحسمه الهجرة.
- **OWN-31** على المالك: حملةُ تفضيلات المعلّمين.
- **SK1..SK5** مؤشّراتٌ بقياس 2026-09-24.

حارسةٌ كسابقاتها: كلُّ إنشاءٍ يتخطّى ما وُجد برمزه، ولا تلمس بنداً قائماً. **التواريخُ والجهدُ من خطّة الجلسة
مقترَحةٌ لم يعتمدها المالك**، ولا رقمَ طلبٍ بعدُ لأيّ بند: يُضاف برقم طلبه في مزامنةٍ لاحقة حين يندمج.
"""

import datetime

from django.db import migrations

STAMP = "[2026-09-24]"
DAY = datetime.date(2026, 9, 24)
D = datetime.date
BASIS = "مقترَح — من خطّة جلسة الجدولة، لم يعتمده المالك"
REF = "docs/schedule_generation_remediation_plan_2026-09.md"

URGENT = "عاجلٌ قبل العمل بالجدول الجديد الأحد 2026-09-27."
PHASE_1 = "المرحلةُ الأولى (أسبوعان)."
PHASE_2 = "المرحلةُ الثانية (شهر)؛ يلزمها قرارٌ معماريّ مكتوب (ADR)."

# (الرمز، المسار، العنوان، البداية، النهاية، الجهد، الاعتماديّات، معيار الإغلاق، الحالة، التقدّم، البوّابة، ملاحظة)
SCH_ITEMS = [
    (
        "SCH-01",
        "backend",
        "مصدرٌ واحدٌ لصحّة الخانة: slot_violations وis_slot_valid يسمّيان القيدَ الذي يرفض الحصّة",
        D(2026, 9, 24),
        D(2026, 9, 24),
        0.25,
        "",
        "slot_violations وis_slot_valid من مصدرٍ واحد، واختبارٌ يطابقهما.",
        "doing",
        60,
        "",
        URGENT,
    ),
    (
        "SCH-02",
        "backend",
        "مدقّقٌ مستقلٌّ للجدول النهائيّ يعدّ المخالفاتِ الصلبة بأسماء قيودها",
        D(2026, 9, 24),
        D(2026, 9, 25),
        0.5,
        "SCH-01",
        "المدقّقُ يكشف مخالفاتِ الإنتاج الاثنتي عشرة، وصفراً على شبكةٍ نظيفة.",
        "doing",
        10,
        "",
        URGENT,
    ),
    (
        "SCH-03",
        "backend",
        "مرحلةُ سدادٍ بعد التوليد تُنزل المخالفاتِ الصلبة قبل الحفظ",
        D(2026, 9, 24),
        D(2026, 9, 25),
        1,
        "SCH-02",
        "مرحلةُ السداد تُنزل مخالفاتِ نسخة الإنتاج من 12 بلا متعذّر، باختبار وحدة.",
        "doing",
        5,
        "",
        URGENT,
    ),
    (
        "SCH-04",
        "backend",
        "المخالفاتُ تُحفظ مع النسخة: قائمتُها في config_snapshot وعددُها في hard_violations",
        D(2026, 9, 25),
        D(2026, 9, 25),
        0.25,
        "SCH-02",
        'قائمةُ المخالفات في config_snapshot["breaches"] وعددُها في hard_violations.',
        "doing",
        0,
        "",
        URGENT,
    ),
    (
        "SCH-05",
        "backend",
        "بوّابةُ الاعتماد: صفحةُ الجدول الذكيّ تعرض المخالفات، والاعتمادُ معها يلزمه إقرار",
        D(2026, 9, 25),
        D(2026, 9, 26),
        0.5,
        "SCH-04، D-17",
        "صفحةُ الجدول الذكيّ تعرض المخالفات، والاعتمادُ معها يلزمه إقرارٌ صريح.",
        "doing",
        0,
        "owner",
        f"{URGENT} يحجبه قرارُ المالك D-17.",
    ),
    (
        "SCH-06",
        "backend",
        "أمرُ إدارةٍ يكتب مسودّةً من الجدول الحيّ بمخالفاتٍ أقلّ وفرقٍ محدود",
        D(2026, 9, 25),
        D(2026, 9, 26),
        0.75,
        "SCH-03",
        "أمرُ إدارةٍ يكتب مسودّةً من الجدول الحيّ بمخالفاتٍ أقلّ وفرقٍ محدود، تُعتمد بعد الدوام.",
        "todo",
        0,
        "",
        URGENT,
    ),
    (
        "SCH-07",
        "ops",
        "الاحتفاظُ بنسختين على الأقلّ من الجدول على الإنتاج",
        D(2026, 9, 25),
        D(2026, 9, 26),
        0.1,
        "",
        "SCHEDULE_ARCHIVE_RETENTION ≥ 2 على الإنتاج.",
        "todo",
        0,
        "",
        URGENT,
    ),
    (
        "SCH-08",
        "backend",
        "حصصُ الأحد تطابق الجدولَ الجديد: الاعتمادُ يُعيد مزامنةَ الحصص إلى آخر تاريخٍ مولَّد",
        D(2026, 9, 26),
        D(2026, 9, 26),
        0.25,
        "SCH-06، #531 (resync_sessions_for_range)",
        "حصصُ الأحد 2026-09-27 تطابق الجدولَ الجديد، وapprove_generation يستدعي resync_sessions_for_range "
        "من اليوم إلى آخر تاريخٍ مولَّد.",
        "todo",
        0,
        "",
        f"{URGENT} الواجهةُ resync_sessions_for_range اندمجت ونُشرت بـ#531 (N-032)، ومصالحةُ الأسابيع "
        "المولَّدة سلفاً عند الاعتماد جزءٌ من هذا البند (اتّفاق جلستَي الجدولة و«اصلاحات 01»).",
    ),
    (
        "SCH-09",
        "backend",
        "المحسِّنُ (Improver) يرفض كلَّ حركةٍ تزيد المخالفاتِ الصلبة",
        D(2026, 9, 28),
        D(2026, 10, 2),
        1,
        "SCH-02",
        "Improver يرفض كلَّ حركةٍ تزيد المخالفاتِ الصلبة، ومختبرُ الجودة لا يسوء.",
        "todo",
        0,
        "",
        PHASE_1,
    ),
    (
        "SCH-10",
        "backend",
        "مؤشّرُ عدالة الشُّعب في تحمّل الرخص في مختبر الجودة",
        D(2026, 9, 28),
        D(2026, 10, 2),
        0.5,
        "SCH-02",
        "مؤشّرُ عدالة الشُّعب في تحمّل الرخص في المختبر، بقياس أساس.",
        "todo",
        0,
        "",
        PHASE_1,
    ),
    (
        "SCH-11",
        "backend",
        "أوزانُ القيود الليّنة تُضبط بالقياس لا بالتقدير",
        D(2026, 9, 29),
        D(2026, 10, 8),
        2,
        "SCH-10",
        "كلُّ وزنٍ يتغيّر بقياسٍ موثّق، والرياضيّاتُ في الحصّتين 6 و7 ≤ 15% (SK4).",
        "todo",
        0,
        "",
        PHASE_1,
    ),
    (
        "SCH-12",
        "backend",
        "ثباتُ التوليد: تباينُ الدرجة بين البذور ينخفض إلى النصف",
        D(2026, 10, 1),
        D(2026, 10, 8),
        2,
        "SCH-09",
        "تباينُ الدرجة بين البذور ينخفض إلى النصف.",
        "todo",
        0,
        "",
        PHASE_1,
    ),
    (
        "SCH-13",
        "backend",
        "البحثُ بالجوار الواسع (LNS) بمحلّل CP-SAT: حلٌّ بلا كسرٍ أو برهانُ استحالة",
        D(2026, 10, 5),
        D(2026, 10, 23),
        5,
        "ADR، SCH-16",
        "حلٌّ بلا كسرٍ أو برهانُ استحالة، وزمنُه مقيسٌ على Railway.",
        "todo",
        0,
        "owner",
        PHASE_2,
    ),
    (
        "SCH-14",
        "backend",
        "استقرارُ الجدول: تغييرُ إسنادٍ واحد لا يقلب الجدول",
        D(2026, 10, 12),
        D(2026, 10, 23),
        3,
        "SCH-13",
        "تغييرُ إسنادٍ واحد يحرّك أقلَّ من 5% من الحصص.",
        "todo",
        0,
        "",
        PHASE_2,
    ),
    (
        "SCH-15",
        "backend",
        "رسالةُ التعذّر بأسماء القيود المتعارضة بدل «تعذّر وضع»",
        D(2026, 10, 12),
        D(2026, 10, 23),
        2,
        "SCH-13",
        "رسالةٌ بأسماء القيود المتعارضة بدل «تعذّر وضع».",
        "todo",
        0,
        "",
        PHASE_2,
    ),
    (
        "SCH-16",
        "backend",
        "تقسيمُ المولّد حسب المسؤوليّة: لا ملفَّ فيه فوق 1000 سطر",
        D(2026, 9, 29),
        D(2026, 10, 9),
        3,
        "",
        "لا ملفَّ في المولّد فوق 1000 سطر.",
        "todo",
        0,
        "",
        PHASE_2,
    ),
]
SCH_FIRST_ORDER = 601  # كتلةٌ مستقلّة بعد N-… (463) تتّسع لبنود N القادمة

OWN_ITEM = {
    "code": "OWN-31",
    "src": "OWN",
    "lane": "product",
    "title": "حملةُ جمع تفضيلات المعلّمين للجدول (في القاعدة اليوم ثلاثةُ صفوفٍ فقط)",
    "status": "todo",
    "progress": 0,
    "start_date": D(2026, 9, 28),
    "end_date": D(2026, 10, 8),
    "date_basis": BASIS,
    "effort": 1,
    "deps": "",
    "criterion": "تفضيلاتُ المعلّمين مجموعةٌ في المنصّة قبل التوليد التالي؛ حدُّ الاكتمال يحدّده المالك.",
    "gate": "owner",
    "ref": REF,
    "sort_order": 255,  # بعد OWN-30 (254)
}

DECISION = {
    "code": "D-17",
    "src": "SCH",
    "title": "رخصةُ الكثافة HC6: تبقى ملاذاً أخيراً مع السداد وبوّابة الاعتماد، أم تُمنع؟",
    "status": "open",
    "decider": "المالك",
    "due": "2026-09-26 (قبل SCH-05)",
    "blocks": "SCH-05",
    "options": "(أ) تبقى ملاذاً أخيراً، بعد مرحلة السداد (SCH-03) وخلف بوّابة الاعتماد (SCH-05). "
    "(ب) تُمنع: ما يتعذّر وضعُه بلا كسرٍ لا يُولَّد.",
    "recommendation": "(أ) تبقى، على ألّا يُعتمد جدولٌ فيه مخالفةٌ لم يُقرّ بها المعتمِد صراحةً (توصيةُ جلسة الجدولة).",
    "sort_order": 115,  # بعد D-16 (114)
}

# (الرمز، الاسم، القيمة اليوم، الهدف، الهدف نصّاً، الاتّجاه، الوحدة)
KPIS = [
    ("SK1", "المخالفاتُ الصلبة في الجدول المعتمد", 12.0, 0.0, "", "down", "count"),
    ("SK2", "توزيعُ المادّة على أيّام الأسبوع", 98.2, 100.0, "", "up", "pct"),
    ("SK3", "أيّامُ التلاصق المخالف", 17.9, 10.0, "≤ 10%", "down", "pct"),
    ("SK4", "الرياضيّاتُ في الحصّتين السادسة والسابعة", 26.0, 15.0, "≤ 15%", "down", "pct"),
    ("SK5", "النسخُ المحفوظة من الجدول", 0.0, 2.0, "≥ 2", "up", "count"),
]
KPI_FIRST_ORDER = 412  # بعد LK5 (411)
KPI_SOURCE = "تدقيقُ الجدول الحيّ 2026-09-24 (جلسة الجدولة)"


def add_items(item_model):
    """تُنشئ بنودَ الخطّة الغائبة وبندَ المالك؛ تُرجع رموزَ ما أُنشئ."""
    created = []
    for offset, row in enumerate(SCH_ITEMS):
        code, lane, title, start, end, effort, deps, criterion, status, progress, gate, note = row
        if item_model.objects.filter(code=code).exists():
            continue
        item_model.objects.create(
            code=code,
            src="SCH",
            lane=lane,
            title=title,
            status=status,
            progress=progress,
            start_date=start,
            end_date=end,
            date_basis=BASIS,
            effort=effort,
            deps=deps,
            criterion=criterion,
            note=f"{STAMP} {note}",
            gate=gate,
            ref=REF,
            sort_order=SCH_FIRST_ORDER + offset,
        )
        created.append(code)
    if not item_model.objects.filter(code=OWN_ITEM["code"]).exists():
        item_model.objects.create(
            **OWN_ITEM, note=f"{STAMP} من خطّة إصلاح توليد الجدول؛ على المالك."
        )
        created.append(OWN_ITEM["code"])
    return created


def add_decision(decision_model):
    """تُنشئ D-17 مفتوحاً إن غاب؛ لا تحسمه."""
    if decision_model.objects.filter(code=DECISION["code"]).exists():
        return []
    decision_model.objects.create(**DECISION)
    return [DECISION["code"]]


def add_kpis(kpi_model):
    """تُنشئ المؤشّراتِ الغائبة بقياسها الأوّل؛ تُرجع رموزَ ما أُنشئ."""
    created = []
    for offset, (code, name, value, target, target_text, direction, unit) in enumerate(KPIS):
        if kpi_model.objects.filter(code=code).exists():
            continue
        kpi_model.objects.create(
            code=code,
            lane="backend",
            name=name,
            baseline=value,
            current=value,
            target=target,
            target_text=target_text,
            direction=direction,
            unit=unit,
            source=KPI_SOURCE,
            measured_at=DAY,
            history=[{"d": DAY.isoformat(), "v": value}],
            extra={"basis": "الهدفُ من خطّة جلسة الجدولة، مقترَحٌ لم يعتمده المالك", "ref": REF},
            sort_order=KPI_FIRST_ORDER + offset,
        )
        created.append(code)
    return created


def forwards(apps, schema_editor):
    item_model = apps.get_model("roadmap", "RoadmapItem")
    # قاعدةٌ بلا استيراد (اختبار، شجرةٌ جديدة): لا شيء يُزامَن، ولا بنودٌ يتيمة.
    if not item_model.objects.exists():
        return
    add_items(item_model)
    add_decision(apps.get_model("roadmap", "RoadmapDecision"))
    add_kpis(apps.get_model("roadmap", "RoadmapKpi"))


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0011_sync_items_2026_09_24c"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
