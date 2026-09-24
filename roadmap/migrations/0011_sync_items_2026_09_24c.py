"""مزامنةُ الخارطة الثالثة يومَ 2026-09-24، بعد دمج #508 #514 #518 #519 #524 #526.

حارسةٌ كـ0009: لا تلمس بنداً إلّا إن كانت حالتُه وتقدّمُه ما في آخر لقطة؛ والملاحظةُ الموجودة لا تُلحَق
ثانيةً؛ والبندُ الجديد يُنشأ إن غاب. وتزيد عليها **أوّلَ تحديثٍ لمؤشّراتٍ في هجرة**: مؤشّراتُ التخطيط
LK1..LK5 بقياس main@917a5bab، ولا يُلمس مؤشّرٌ إلّا إن كانت قيمتُه وتاريخُ قياسه ما في آخر لقطة.

- **VI-28** يُغلق بـ#519 (صفحتا الدليل والأيقونات). و**H-06** يبدأ بـ#519 (scale_tokens بستّة سلالم) —
  وأقسامُ الدليل الثمانيةُ الجديدة جزءٌ منه لا بندٌ مستقلّ.
- **OWN-19** إلى 90 بـ#526 (يُغلق مع بقيّة axes)، و**OWN-21** إلى 50 بـ#508.
- **LAY-03 لا يُلمس:** مرحلتُه الأولى في فرعٍ لم يُدمج، ولا يُدرج عملٌ قبل اندماج طلبه.
"""

import datetime

from django.db import migrations

STAMP = "[2026-09-24]"
DAY = datetime.date(2026, 9, 24)

# (الرمز، (الحالة، التقدّم) المتوقَّعان، الحالة الجديدة، التقدّم الجديد، طلب الدمج، سطر الملاحظة)
# الحالةُ الجديدة كالمتوقَّعة = ملاحظةُ تقدّمٍ وحدها.
UPDATES = [
    (
        "VI-28",
        ("todo", 0),
        "done",
        100,
        "#519",
        "أُغلق: #519 بطاقاتُ الدليل متجاورةٌ بعرض حاجتها، والأسسُ الناقصة، وصفحةُ الأيقونات مجموعات.",
    ),
    (
        "H-06",
        ("todo", 0),
        "doing",
        40,
        "#519",
        "#519: scale_tokens تعرض ستّة سلالم من :root (text وlh وsp وradius وshadow وtransition) في ثمانية "
        "أقسامٍ جديدة بالدليل. الباقي: سلّما control-h وz-* (وsafe-* بعد H-04) في _SCALES، وقسمُ «المقاييس "
        "والحدود الدنيا»، وقواعدُ القسم 8.",
    ),
    (
        "VI-29",
        ("todo", 0),
        "todo",
        0,
        "",
        "#519 وضع أوّلَ لبنة: card-flow في 20-components.css ومعاملُ span في section_card.",
    ),
    (
        "OWN-19",
        ("todo", 0),
        "doing",
        90,
        "#526",
        "#526: verbose_name عربيٌّ لـ470 حقلاً في 17 تطبيقاً، وجمعٌ عربيٌّ لثلاثة نماذج، و13 هجرةً بلا SQL، "
        "والحارس tests/test_model_field_labels_arabic.py. يُغلق بطلب بقيّة axes.",
    ),
    (
        "OWN-21",
        ("todo", 0),
        "doing",
        50,
        "#508",
        "#508: ذيلُ الإدارة بمعلَمٍ واحد (div لا footer ثانٍ)، ولا رابطَ داخل summary، واسمٌ مخفيٌّ لكلّ خليّةٍ "
        "في tabular.html ومنها خانةُ الحذف، والجداولُ المضمَّنة في table-wrap. الباقي: الفحصُ الليليّ "
        "والتباينُ وترتيبُ التبويب.",
    ),
    (
        "DBT-36",
        ("todo", 0),
        "todo",
        0,
        "",
        "#517 أنقص 2,348 بايتاً من المشحون؛ وLAY-03 يُتوقَّع أن ينقص نحو 1,700 حين يندمج.",
    ),
]

# بنودٌ جديدةٌ لعملٍ دُمج بلا بند: (الرمز، المسار، العنوان، طلب الدمج، ملاحظةٌ إضافيّة)
NEW_ITEMS = [
    (
        "N-029",
        "backend",
        "التبديلُ بسبب الغياب مع معلّمي الشعبة: موافقةٌ ثمّ توقيعا المنسّقَين ثمّ اعتمادُ النائب",
        "#524",
        "",
    ),
    (
        "N-030",
        "desktop",
        "سجلّاتُ الدخول (axes) في الإدارة: الاسمُ والرقمُ الوظيفيّ، والرقمُ الشخصيّ مخفيّ",
        "#518",
        "عمودان في القوائم الثلاث باستعلامٍ فرعيٍّ واحد، ولا يظهر من الرقم الشخصيّ إلّا آخرُ أربعة.",
    ),
    (
        "N-031",
        "desktop",
        "الإدارة بلا N+1: قوائمُ لا تسأل لكلّ صفّ",
        "#514",
        "list_select_related وجلبُ العضويّات مسبقاً (373←25 استعلاماً)، والحارس "
        "tests/test_admin_changelist_queries.py.",
    ),
]

NEW_ITEMS_FIRST_ORDER = 461  # بعد N-028 (460)

# (الرمز، (القيمة، تاريخ القياس) المتوقَّعان، القيمة الجديدة)
KPI_MEASURED = datetime.date(2026, 9, 23)
KPI_UPDATES = [
    ("LK1", (0.0, KPI_MEASURED), 0.0),
    ("LK2", (9.0, KPI_MEASURED), 10.0),
    ("LK3", (24.3, KPI_MEASURED), 24.0),
    ("LK4", (11.0, KPI_MEASURED), 11.0),
    ("LK5", (1088.0, KPI_MEASURED), 998.0),
]
KPI_SOURCE_NOTE = "قياس main@917a5bab"


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


def sync_kpis(kpi_model):
    """تُحدِّث المؤشّراتِ التي لم تُمسّ منذ آخر لقطة، وتحفظ القياسين في سجلّها؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, expected, value in KPI_UPDATES:
        kpi = kpi_model.objects.filter(code=code).first()
        if kpi is None or (kpi.current, kpi.measured_at) != expected:
            continue
        history = list(kpi.history or [])
        dates = {point.get("d") for point in history}
        if expected[1].isoformat() not in dates:
            history.append({"d": expected[1].isoformat(), "v": expected[0]})
        history.append({"d": DAY.isoformat(), "v": value})
        kpi.current, kpi.measured_at, kpi.history = value, DAY, history
        if KPI_SOURCE_NOTE not in kpi.source:
            kpi.source = f"{kpi.source} ({KPI_SOURCE_NOTE})".strip()
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
    sync_kpis(apps.get_model("roadmap", "RoadmapKpi"))


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0010_owner_items_from_snapshot"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
