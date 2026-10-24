"""الخارطةُ السابعةُ والستّون (2026-10-22): دمجُ #1212 (N-153) و#1219 (N-154) بندين جديدين، و#1222 ملاحظةً على N-108.

حارسةٌ كسابقاتها: لا يُنشأ بندٌ موجود، ولا ملاحظةَ تتكرّر، ولا حالةَ أو تقدّمَ لبندٍ قائمٍ يُلمس.
**المقيس:** الإيداعات في main (فحصُ git)؛ لم أقِس الإنتاجَ ولا الاستعمالَ الفعليّ. لا هجرةَ بنيويّةً ولا صلاحيةَ في الطلبات.
**المستودعُ عامّ:** نصوصٌ محايدةٌ بلا أسماءٍ ولا مفاتيح.
"""

import datetime

from django.db import migrations

STAMP = "[2026-10-22]"
DAY = datetime.date(2026, 10, 21)

# (الرمز، المصدر، المسار، العنوان، الاعتماديّات، المعيار، الحالة، التقدّم، البداية، النهاية،
# أساسُ التاريخ، الجهد، البوّابة، الطلب، المرجع، الملاحظة، ترتيبُ الفرز)
NEW_ITEMS = [
    (
        "N-153",
        "N",
        "behavior",
        "بريدُ المخالفة بصيغةٍ محايدة",
        "",
        "نصُّ بريد المخالفة محايدٌ لا يحمل تفاصيلَ حسّاسة؛ اختبارٌ يثبّت الصيغة.",
        "done",
        100,
        DAY,
        DAY,
        "#1212 اندمج 2026-10-21 (الإيداع f50e2359)",
        1.0,
        "",
        "#1212",
        "W-20261012-031",
        "**بندٌ جديد.** **المقيس:** الإيداعُ في main. لم يُقَس أثرُه على الاستعمال الفعليّ.",
        887,
    ),
    (
        "N-154",
        "N",
        "design",
        "وسمُ page_layout في اثني عشر قالباً",
        "",
        "كلُّ قالبٍ من الاثني عشر يحمل وسمَ التخطيط؛ وحارسُ تخطيط الصفحات يمرّ.",
        "done",
        100,
        DAY,
        DAY,
        "#1219 اندمج 2026-10-21 (الإيداع 717f2505)",
        1.0,
        "",
        "#1219",
        "W-20261011-003",
        "**بندٌ جديد.** **المقيس:** الإيداعُ في main. لم يُقَس أثرُه على الاستعمال الفعليّ.",
        888,
    ),
]

NOTES = [
    (
        "N-108",
        "#1222",
        "اندمج #1222 (2026-10-21، W-20261016-005): رمزُ حجمٍ جديد --text-xs-plus يوحّد 20 موضعاً، وأربعةُ مواضع clamp بحدٍّ أدنى 12px، "
        "وحارسُ no_font_size_below_12px. **التقدّم:** التوصيتان 4 و6 منجزتان ويبقى --touch-target. **لم يُقَس** أثرُه على الاستعمال "
        "الفعليّ. لا تغيّرَ في الحالة أو التقدّم.",
    ),
]


def _add_pr(existing, token):
    """تُضيف رمزَ الطلب دون تكرارٍ ودون تجاوز حدّ الحقل 64 (وإلّا يبقى الحقلُ كما هو)."""
    if not token:
        return existing
    joined = " ".join(dict.fromkeys([*existing.split(), *token.split()]))
    return joined if len(joined) <= 64 else existing


def add_new_items(item_model):
    """تُنشئ البنودَ الغائبة؛ لا تُعيد كتابةَ بندٍ موجود؛ تُرجع رموزَ ما أُنشئ."""
    created = []
    for (
        code,
        src,
        lane,
        title,
        deps,
        criterion,
        status,
        progress,
        start,
        end,
        basis,
        effort,
        gate,
        pr,
        ref,
        note,
        order,
    ) in NEW_ITEMS:
        if item_model.objects.filter(code=code).exists():
            continue
        item_model.objects.create(
            code=code,
            src=src,
            lane=lane,
            title=title,
            status=status,
            progress=progress,
            start_date=start,
            end_date=end,
            date_basis=basis,
            effort=effort,
            deps=deps,
            criterion=criterion,
            gate=gate,
            pr=pr,
            ref=ref,
            note=f"{STAMP} {note}",
            sort_order=order,
        )
        created.append(code)
    return created


def sync_notes(item_model):
    """تُلحق الملاحظاتِ ورمزَ الطلب بالبنود القائمة مرّةً واحدة بلا لمس الحالة؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, pr, line in NOTES:
        item = item_model.objects.filter(code=code).first()
        if item is None or line in item.note:
            continue
        item.note = f"{item.note}\n{STAMP} {line}".strip()
        item.pr = _add_pr(item.pr, pr)
        item.save(update_fields=["note", "pr", "updated_at"])
        changed.append(code)
    return changed


def forwards(apps, schema_editor):
    item_model = apps.get_model("roadmap", "RoadmapItem")
    # قاعدةٌ بلا استيراد (اختبار، شجرةٌ جديدة): لا شيء يُزامَن.
    if not item_model.objects.exists():
        return
    add_new_items(item_model)
    sync_notes(item_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0082_sync_items_2026_10_21"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
