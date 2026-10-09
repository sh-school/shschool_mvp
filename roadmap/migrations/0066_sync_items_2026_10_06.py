"""الخارطةُ الثانيةُ والخمسون (2026-10-06): نشرُ #874 (الرصدُ بحصّةٍ مؤقّتة للمعلّم ومنتقي الحصص الوحيد)، وبندٌ جديدٌ N-096.

حارسةٌ كسابقاتها: لا يُنشأ بندٌ موجود، ولا يُعاد كتابةُ ما عدّله المطوّر، ولا تُكرَّر ملاحظة.

**N-096 (#874):** منشورٌ ومفعَّلٌ على الإنتاج بمفتاحٍ مفعَّل بقرار المالك D-229م (إبلاغُ جلسة النشر)؛ والقياسُ الفعليّ لم يُجرَ فيبقى doing.
**لماذا بندٌ جديد:** لا بندَ قائمٌ يغطّيه في المصدر المتاح؛ فإن ظهر مقابلٌ في الإنتاج فيُدمَج بقرار 0701 لا بصمت.
**المستودعُ عامّ:** نصوصٌ محايدةٌ بلا تفاصيل ثغراتٍ ولا بياناتٍ شخصيّة.
"""

import datetime

from django.db import migrations

STAMP = "[2026-10-05]"
D = datetime.date
DAY = D(2026, 10, 5)

# بنودٌ جديدة: (الرمز، المصدر، المسار، العنوان، الاعتماديّات، المعيار، الحالة، التقدّم، البداية، النهاية،
# أساسُ التاريخ، الجهد، البوّابة، الطلب، المرجع، الملاحظة، ترتيبُ الفرز)
NEW_ITEMS = [
    (
        "N-096",
        "N",
        "backend",
        "رصدُ الغياب بحصّةٍ مؤقّتة للمعلّم ومنتقي الحصص ح1–ح7 الوحيد (هجرتا operations 0070 و0071)",
        "",
        "الاستعمالُ الفعليّ يسجّل رصداً بحصّةٍ مؤقّتة، ودخولُ معلّمٍ حقيقيّ مُتحقَّقٌ منه، وجدولُ الحصص يحتمل القيدين الجزئيّين بلا شذوذ.",
        "doing",
        70,
        DAY,
        DAY,
        "W-20261005-006، #874 نُشر e80a2c7 (2026-10-06، إبلاغُ جلسة النشر؛ /health/ يعلنه)",
        2.0,
        "",
        "#874",
        "",
        "**بندٌ جديدٌ بقاعدة الإدراج (لا بندَ قائمٌ يغطّيه في المصدر المتاح).** اندمج بسطر اعتمادٍ على رأسه؛ "
        "هجرتا operations 0070 و0071 طُبّقتا (عمودان وقيدان جزئيّان على جدول الجلسات)، والمفتاحُ مفعَّلٌ على الويب بقرار المالك D-229م. "
        "(التقدّمُ تقديريٌّ بعدّ المراحل لا قياسُ أثر.) **لم يُقَس** أثرُه على الاستعمال الفعليّ، ولا فحصُ دخول معلّمٍ حقيقيّ. "
        "وفشلت ثلاثةُ فحوصِ Analyze (CodeQL) على رأس الطلب وقتَ دمجه ولم تُحسم بعدُ في قراءتي.",
        824,
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
    add_new_items(item_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0065_sync_items_2026_10_05b"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
