"""الخارطةُ الرابعةُ والستّون (2026-10-15): بندان نُشرا بأمر 0101 — N-148 (قسم إنهاء الجلسة) وN-149 (تقليص CLAUDE.md).

حارسةٌ كسابقاتها: لا يُنشأ بندٌ موجود ولا ملاحظةَ تتكرّر. **المقيسُ عند 0101 (فحصُ main وسجلُّ verified في الدفتر)؛ لم أقِس الإنتاج.**
**المستودعُ عامّ:** نصوصٌ محايدةٌ بلا أسماءٍ ولا مفاتيح.
"""

import datetime

from django.db import migrations

STAMP = "[2026-10-15]"
DAY = datetime.date(2026, 10, 15)

# (الرمز، المصدر، المسار، العنوان، الاعتماديّات، المعيار، الحالة، التقدّم، البداية، النهاية،
# أساسُ التاريخ، الجهد، البوّابة، الطلب، المرجع، الملاحظة، ترتيبُ الفرز)
NEW_ITEMS = [
    (
        "N-148",
        "N",
        "tools",
        "قسمُ «إنهاء الجلسة» في وثيقة خادم الجلسة: إيقافٌ بـstop لا down -v",
        "",
        "الوثيقةُ تنصّ على إنهاء الجلسة بإيقاف الحاويات دون حذف قاعدة الجلسة.",
        "done",
        100,
        DAY,
        DAY,
        "#1085 اندمج 2026-10-15 (الإيداع 485a1bd85)",
        0.25,
        "",
        "#1085",
        "W-20261015-019",
        "**بندٌ جديد.** وثائقُ فقط (docs/deployment/session_server.md). **المقيسُ عند 0101:** الإيداعُ في main وسُجّل verified في الدفتر. لا أثرَ على الإنتاج.",
        882,
    ),
    (
        "N-149",
        "N",
        "tools",
        "تقليصُ CLAUDE.md إلى 93 سطراً بنقلٍ حرفيّ إلى ملفّاتٍ مرجعيّة",
        "",
        "لا قاعدةٌ تضيع: النصُّ المنقول حرفيٌّ في ملفّات المرجع، واختبارٌ يحرسه.",
        "done",
        100,
        DAY,
        DAY,
        "#1086 اندمج 2026-10-15 (الإيداع b90bdce0a)",
        0.5,
        "",
        "#1086",
        "W-20261015-020",
        "**بندٌ جديد.** نُقل النصُّ إلى .claude/rules/deploy-window.md ووثيقتَي local_preview وsession_server، ويحرسه tests/test_claude_md_moved_text.py. **المقيسُ عند 0101:** الإيداعُ في main وسُجّل verified. لا أثرَ على الإنتاج.",
        883,
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
        ("roadmap", "0078_closed_items_verification_2026_10_15"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
