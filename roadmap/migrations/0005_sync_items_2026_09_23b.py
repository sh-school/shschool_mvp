"""مزامنةُ الخارطة الثانية يومَ 2026-09-23: DBT-22 وN-014.

حارسةٌ كـ0003/0004: لا تلمس بنداً إلّا إن كانت حالتُه وتقدّمُه ما في آخر لقطة، والملاحظةُ
الموجودة لا تُلحَق ثانيةً، والبندُ الجديد يُنشأ إن غاب.
"""

import datetime

from django.db import migrations

STAMP = "[2026-09-23]"
DAY = datetime.date(2026, 9, 23)

# (الرمز، (الحالة، التقدّم) المتوقَّعان، الحالة الجديدة، التقدّم الجديد، طلب الدمج، سطر الملاحظة)
UPDATES = [
    (
        "DBT-22",
        ("todo", 0),
        "done",
        100,
        "#492",
        "أُغلق: #492 جعل seed_data.py يرفض العمل خارج shschool.settings.development؛"
        " وreal_seed.py لا كلمةَ مرورٍ فيه (يشترط SEED_DEFAULT_PASSWORD).",
    ),
]

# عملٌ دُمج بلا بندٍ في الخارطة: (الرمز، المسار، العنوان، طلب الدمج)
NEW_ITEMS = [
    (
        "N-014",
        "frontend",
        "لوحة المدير: «نبض المدرسة» صفّان بخمسةٍ خمسة، وشريطُ الخمسة صفٌّ واحدٌ على العريض",
        "#491",
    ),
]

NEW_ITEMS_FIRST_ORDER = 439  # بعد N-013 (438)


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
    add_missing(item_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0004_sync_items_2026_09_23"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
