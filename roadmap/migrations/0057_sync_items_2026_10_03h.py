"""الخارطةُ الثالثةُ والأربعون (2026-10-03): نشرُ #797 (shards pytest) وقراءةُ 0702 بعده، وبندُ قاعدة التنبيهات D-170م (#826).

حارسةٌ كسابقاتها: لا تُكرَّر ملاحظةٌ، ولا يُنشأ بندٌ موجود، ولا بندَ يُغلق بلا قياسٍ أو نشرٍ مؤكَّد.

**#797:** نُشر بتأكيد جلسة النشر (الإنتاج 3ebbc2e)؛ ولقطتان فقط عند 0702 فلا اتّجاه.
**N-084 (#826):** نصُّ قاعدةٍ فقط في design-system.md؛ لا شيفرة، فلا يُنسب إليه قياسُ أثر.

والمستودعُ عامّ: نصوصٌ محايدة بلا تفاصيل ثغراتٍ ولا بياناتٍ شخصيّة.
"""

import datetime

from django.db import migrations

STAMP = "[2026-10-03]"
D = datetime.date
DAY = D(2026, 10, 3)

# ملاحظاتٌ على بنودٍ قائمة تُلحق مرّةً واحدة بلا لمس الحالة ولا التقدّم: (الرمز، السطر)
NOTES = [
    (
        "N-069",
        "**#797 نُشر (تأكيدُ جلسة النشر: الإنتاجُ على 3ebbc2e):** ما سبق عن «لا تأكيدَ نشرٍ» صار قديماً. "
        "**قراءةُ 0702 على main@3ebbc2ef (أوّلُ تشغيلين مقسَّمين، لا اتّجاه):** التغطيةُ المدموجة 87.84% (87.83% في push)، والناجحُ في الشظايا 11,289، وزمنُ البوّابة نحو 14.3–14.6 دقيقة (كان نحو 20)، واللقطاتُ ناجحة. "
        "**لم يُقَس** اتّجاهٌ عبر تشغيلاتٍ أكثر، ولا زمنُ الدورة عند المطوّرين.",
    ),
    (
        "SCH-23",
        "**قراءةُ 0702 بعد shards pytest (#797، main@3ebbc2ef، تشغيلان):** زمنُ البوّابة الكلّيّ نحو 14.3–14.6 دقيقة؛ وaxe (نحو 14 دقيقة) صار على المسار الحرج مع الـshard الأوّل. "
        "**لقطتان فقط فلا اتّجاه**؛ وهي ارتباطٌ لا إسنادُ سببٍ لتغيّر المدّة.",
    ),
]

# بنودٌ جديدة: (الرمز، المصدر، المسار، العنوان، الاعتماديّات، المعيار، الحالة، التقدّم، البداية، النهاية، أساسُ التاريخ، الجهد، البوّابة، طلب الدمج، المرجع، الملاحظة، الترتيب)
NEW_ITEMS = [
    (
        "N-084",
        "N",
        "frontend",
        "قاعدةُ التنبيهات: أيقونةٌ لكلّ نوعٍ في شريط عنوان البطاقة (D-170م)",
        "",
        "نصُّ القاعدة في .claude/rules/design-system.md: التلميحُ والتحذيرُ والخطأ أيقوناتٌ في شريط عنوان البطاقة لا داخلها يظهر نصُّها بالمرور، مع استثناء ui-note وui-field-hint بلا شارة؛ **ثمّ** حارسٌ نصّيٌّ يرفض المخالف (لم يكن في ملفّات #826).",
        "doing",
        50,
        DAY,
        None,
        "W-20261003-033، #826 نُشر 7530215 (2026-10-03، الدفتر)",
        0.5,
        "",
        "#826",
        "",
        "**بندٌ جديدٌ بقاعدة الإدراج (لا بندَ قائمٌ يغطّيه).** قرارُ D-170م مسجَّلٌ في decisions.md (أمرُ المالك المباشر في محادثة 0101)، ولا أعدّه تأكيداً مباشراً لهذه الجلسة. "
        "**#826 نصُّ قاعدةٍ فقط (ملفٌّ واحد: +6 −5)، بلا شيفرةٍ**؛ فالتقدّمُ 50% اشتقاقٌ (القاعدةُ كُتبت ولم يُنفَّذ الحارسُ ولا ترحيلُ القوالب) لا قياس. "
        "**لم يُقَس** عددُ التنبيهات المخالفة في القوالب.",
        812,
    ),
]


def _add_pr(existing, token):
    """تُضيف رمزَ الطلب دون تكرارٍ ودون تجاوز حدّ الحقل 64 (وإلّا يبقى الحقلُ كما هو)."""
    if not token:
        return existing
    joined = " ".join(dict.fromkeys([*existing.split(), *token.split()]))
    return joined if len(joined) <= 64 else existing


def sync_notes(item_model):
    """تُلحق الملاحظاتِ بالبنود القائمة مرّةً واحدة بلا لمس الحالة؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, line in NOTES:
        item = item_model.objects.filter(code=code).first()
        if item is None or line in item.note:
            continue
        item.note = f"{item.note}\n{STAMP} {line}".strip()
        item.save(update_fields=["note", "updated_at"])
        changed.append(code)
    return changed


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
            pr=_add_pr("", pr),
            ref=ref,
            note=f"{STAMP} {note}",
            sort_order=order,
        )
        created.append(code)
    return created


def forwards(apps, schema_editor):
    item_model = apps.get_model("roadmap", "RoadmapItem")
    # قاعدةٌ بلا استيراد (اختبار، شجرةٌ جديدة): لا شيء يُزامَن، ولا بنودٌ يتيمة.
    if not item_model.objects.exists():
        return
    sync_notes(item_model)
    add_new_items(item_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0056_sync_items_2026_10_03g"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
