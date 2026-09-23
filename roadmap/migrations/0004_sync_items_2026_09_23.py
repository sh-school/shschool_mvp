"""مزامنةُ الخارطة يومَ 2026-09-23: ديونٌ أغلقتها جلسةُ الباك إند، وحسمُ D-12.

حارسةٌ كـ0003: لا تلمس بنداً إلّا إن كانت حالتُه وتقدّمُه ما في آخر لقطة، ولا قراراً
إلّا إن كان مفتوحاً؛ والملاحظةُ الموجودة لا تُلحَق ثانيةً؛ والبندُ الجديد يُنشأ إن غاب.

D-12 حسمه المالك في المحادثة يومَ 2026-09-23 بعد أن رأى أثرَ طلباته الثلاثة
(#450، #451، #452) على الشاشة، فأُغلق U-30 الذي كان ينتظره وحدَه.
"""

import datetime

from django.db import migrations

STAMP = "[2026-09-23]"
DAY = datetime.date(2026, 9, 23)

# (الرمز، (الحالة، التقدّم) المتوقَّعان، الحالة الجديدة، التقدّم الجديد، طلب الدمج، سطر الملاحظة)
UPDATES = [
    (
        "DBT-08",
        ("todo", 0),
        "done",
        100,
        "#487",
        "أُغلق: #487 حذف deploy.yml المعطَّل ووثيقة أسراره DEPLOYMENT_SECRETS.md.",
    ),
    (
        "DBT-18",
        ("todo", 0),
        "done",
        100,
        "#484",
        "أُغلق: #484 وحّد ruff على 0.4.4 واستثناه دائماً في dependabot.yml.",
    ),
    (
        "DBT-35",
        ("todo", 0),
        "done",
        100,
        "",
        "أُغلق بلا طلب دمج: سطرُ إحالةٍ إلى الخطّة الموحّدة في أعلى خارطة Backend القديمة.",
    ),
    (
        "U-30",
        ("doing", 80),
        "done",
        100,
        "#433 #437 #438 #448",
        "أُغلق: حسم المالكُ D-12 (#450، #451، #452) فلم يبقَ من المرحلة 4 شيء.",
    ),
]

# (الرمز، الحالة المتوقَّعة، الحالة الجديدة)
DECISIONS = [("D-12", "open", "decided")]

# عملٌ دُمج بلا بندٍ في الخارطة: (الرمز، المسار، العنوان، طلب الدمج)
NEW_ITEMS = [
    (
        "N-013",
        "frontend",
        "لوحة المدير: أرقامُ الحضور ونبضُ الأقسام في بطاقةٍ واحدة «نبض المدرسة»",
        "#489",
    ),
]

NEW_ITEMS_FIRST_ORDER = 438  # بعد N-012 (437)


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


def decide(decision_model):
    """تحسم القراراتِ المفتوحة وحدها؛ تُرجع رموزَ ما حُسم."""
    decided = []
    for code, expected, status in DECISIONS:
        decision = decision_model.objects.filter(code=code, status=expected).first()
        if decision is None:
            continue
        decision.status, decision.decision_date = status, DAY
        decision.save(update_fields=["status", "decision_date", "updated_at"])
        decided.append(code)
    return decided


def add_missing(item_model):
    """تُنشئ بنودَ العمل المدموج الغائبة؛ تُرجع رموزَ ما أُنشئ."""
    created = []
    for offset, (code, lane, title, pr) in enumerate(NEW_ITEMS):
        if item_model.objects.filter(code=code).exists():
            continue
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
            note=f"{STAMP} عملٌ دُمج بلا بندٍ في الخارطة، سُجّل مُغلقاً برقم طلبه.",
            sort_order=NEW_ITEMS_FIRST_ORDER + offset,
        )
        created.append(code)
    return created


def forwards(apps, schema_editor):
    item_model = apps.get_model("roadmap", "RoadmapItem")
    # قاعدةٌ بلا استيراد (اختبار، شجرةٌ جديدة): لا شيء يُزامَن، ولا بنودٌ يتيمة.
    if not item_model.objects.exists():
        return
    sync(item_model)
    decide(apps.get_model("roadmap", "RoadmapDecision"))
    add_missing(item_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0003_sync_items_2026_09_22"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
