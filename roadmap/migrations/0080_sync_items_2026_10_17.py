"""الخارطةُ الخامسةُ والستّون (2026-10-17): بندان نُشرا — N-150 (أعمدة متابعة الغياب وخياراتها، #1125) وN-151 (فصل المتابعة إلى صفحتين، #1129).

حارسةٌ كسابقاتها: لا يُنشأ بندٌ موجود ولا ملاحظةَ تتكرّر. **المقيسُ: الإيداعان في main (فحصُ git)؛ لم أقِس الإنتاج.**
**المستودعُ عامّ:** نصوصٌ محايدةٌ بلا أسماءٍ ولا مفاتيح.
"""

import datetime

from django.db import migrations

STAMP = "[2026-10-17]"
DAY = datetime.date(2026, 10, 17)

# (الرمز، المصدر، المسار، العنوان، الاعتماديّات، المعيار، الحالة، التقدّم، البداية، النهاية،
# أساسُ التاريخ، الجهد، البوّابة، الطلب، المرجع، الملاحظة، ترتيبُ الفرز)
NEW_ITEMS = [
    (
        "N-150",
        "N",
        "operations",
        "متابعةُ الغياب: عمودا المتابعة لثلاثة أدوار وخياراتُ التواصل والإجراء والاحتسابُ بالحصّتين الأولى والثانية",
        "",
        "الحجبُ في الخدمة لا في القالب؛ والطباعةُ والتصدير يتبعان الفرزَ والتصفية بقائمةٍ بيضاء.",
        "done",
        100,
        DAY,
        DAY,
        "#1125 اندمج 2026-10-17 (الإيداع 1e79804e1)",
        1.0,
        "",
        "#1125",
        "W-20261014-018",
        "**بندٌ جديد.** قدرةٌ جديدة لمتابعة الغياب وهجرةُ توسيعٍ (0086) وخيارات تواصلٍ وإجراء. **المقيس:** الإيداعُ في main. لم يُقَس أثرُ الإنتاج.",
        884,
    ),
    (
        "N-151",
        "N",
        "operations",
        "فصلُ متابعة الغياب إلى صفحتين (التواصل والإجراءات) وPDF بالاتجاهين",
        "N-150",
        "صفحةٌ بتسعة أعمدةٍ للتواصل وأخرى بثمانيةٍ للإجراءات؛ والمتابعةُ والطباعةُ مفروضتان في الخادم.",
        "done",
        100,
        DAY,
        DAY,
        "#1129 اندمج 2026-10-17 (الإيداع 8fde9f058)",
        1.0,
        "",
        "#1129",
        "W-20261017-024",
        "**بندٌ جديد.** عارضُ PDF بإطارٍ وقائمة عمودي/أفقي، وهجرةٌ (0087) لحقلَي وقت المتابعة ومن سجّلها. **المقيس:** الإيداعُ في main. لم يُقَس أثرُ الإنتاج.",
        885,
    ),
]


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


def forwards(apps, schema_editor):
    item_model = apps.get_model("roadmap", "RoadmapItem")
    # قاعدةٌ بلا استيراد (اختبار، شجرةٌ جديدة): لا شيء يُزامَن.
    if not item_model.objects.exists():
        return
    add_new_items(item_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0079_sync_items_2026_10_15"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
