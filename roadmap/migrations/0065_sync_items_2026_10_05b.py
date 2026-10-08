"""الخارطةُ الحاديةُ والخمسون (2026-10-05): نشرُ #861 (تدقيقُ PDPPL وعزلُ المدارس، المرحلةُ 1)، وبندان جديدان N-094 وN-095.

حارسةٌ كسابقاتها: لا يُنشأ بندٌ موجود، ولا يُعاد كتابةُ ما عدّله المطوّر، ولا تُكرَّر ملاحظة.

**N-094 (#861):** منشورٌ على الإنتاج (إبلاغُ جلسة النشر)؛ مرحلةٌ من مرحلتين فيبقى doing/50.
**N-095:** بندٌ «محجوب» بلا تقدّم حتى يُسنده المالك (قاعدةُ الخارطة: محجوبٌ لا منجز).
**لماذا بندان جديدان:** لا بندَ قائمٌ يغطّيهما في المصدر المتاح؛ فإن ظهر مقابلٌ في الإنتاج فيُدمَج بقرار 0701 لا بصمت.
**المستودعُ عامّ:** نصوصٌ محايدةٌ بلا تفاصيل ثغراتٍ ولا بياناتٍ شخصيّة؛ وتُذكر وثيقةُ التدقيق بمرجعها لا بمضمونها.
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
        "N-094",
        "N",
        "backend",
        "حمايةُ الهاتف في PDPPL: بحثُ الرقم الشخصيّ للإدارة وحدَها، ومنفذُ الهاتف المشفَّر، وإخفاءُ الهاتف والبريد في سجلّ التدقيق (المرحلةُ 1 من مرحلتين)",
        "",
        "المرحلةُ 2 (تفريغُ العمود الصريح) منجزةٌ، ومراجعةُ الأمان ومعاينةُ المالك مسجَّلتان.",
        "doing",
        50,
        DAY,
        DAY,
        "#861 نُشر 9b760a2 (2026-10-05، إبلاغُ جلسة النشر؛ /health/ يعلنه)",
        2.0,
        "",
        "#861",
        "",
        "**بندٌ جديدٌ بقاعدة الإدراج (لا بندَ قائمٌ يغطّيه في المصدر المتاح).** المرحلةُ 1 منشورةٌ بلا هجرات؛ "
        "فحوصُ CI على رأس الطلب ناجحةٌ (31). **ما يبقى:** المرحلةُ 2، ومراجعةُ جلسة الأمان، ومعاينةُ المالك (لم تُسجَّلا). "
        "قياساتُ الجلسة المنفِّذة (اختباراتٌ محلّيّة وزمنُ البحث على جهاز اختبار) إفادةٌ لا قياسي. "
        "**لم يُقَس** أثرُه على بيانات الإنتاج ولا فحوصُ الشاشات بحسابات المالك.",
        822,
    ),
    (
        "N-095",
        "N",
        "backend",
        "عزلُ المستخدمين بين المدارس: إغلاقُ مواضع جلب المستخدم بمعرّفٍ دون فحص المدرسة",
        "",
        "كلُّ موضعٍ مذكورٌ في وثيقة التدقيق يفحص المدرسة، باختبارٍ يحرسه.",
        "blocked",
        0,
        DAY,
        DAY,
        "وثيقةُ docs/privacy/tenant_isolation_audit_2026-10-05.md؛ لا طلبَ مدموج",
        3.0,
        "",
        "",
        "",
        "**محجوب لا منجز:** لا تقدّمَ حتى يُسنده المالك. التفصيلُ في وثيقة التدقيق المذكورة؛ لا يُكرَّر هنا.",
        823,
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
        ("roadmap", "0064_sync_items_2026_10_05"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
