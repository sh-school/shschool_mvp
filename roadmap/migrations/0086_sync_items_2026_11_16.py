"""الخارطةُ السبعون (2026-11-16): هويّةُ «الشحانية» v5 — بندٌ جديدٌ واحدٌ لما اندمج ونُشر (#1447 و#1449، وإصلاحُ CI المصاحب #1448).

حارسةٌ كسابقاتها: لا يُنشأ بندٌ موجود، ولا حالةَ أو تقدّمَ لبندٍ قائمٍ يُلمس.
**المقيس:** الإيداعاتُ في main (فحصُ git)، ونقطةُ الصحّة على الإنتاج تُظهر إيداعَ #1449، والأصلان الجديدان يُخدمان بـ200 (2026-11-16، curl).
**لم يُقَس:** ظهورُ الهويّة على أجهزة المستخدمين ولا تحديثُ أيقونة تطبيقٍ مثبَّت. لا هجرةَ بنيويّةً ولا صلاحيةَ في هذه الهجرة.
**المستودعُ عامّ:** نصوصٌ محايدةٌ بلا أسماءٍ ولا مفاتيح.
"""

import datetime

from django.db import migrations

STAMP = "[2026-11-16]"


def _d(day):
    return datetime.date(2026, 11, day)


# (الرمز، المصدر، المسار، العنوان، المعيار، الحالة، التقدّم، البداية، النهاية، أساسُ التاريخ، الطلبات، المراجع، الملاحظة، ترتيبُ الفرز)
NEW_ITEMS = [
    (
        "VI-60",
        "VI",
        "frontend",
        "هويّةُ «الشحانية» v5: الألوانُ على أنماط التطبيق، والشعارُ الأبيضُ على العنّابيّ في الترويسة والدخول والخطأ، وأيقوناتُ v6",
        "ألوانُ الهويّة من core.brand وأنماط الأساس والسمات؛ الشعارُ الأبيضُ مباشرةً على العنّابيّ بلا شريحة؛ "
        "الأيقوناتُ من الرمز الكامل في مجلّدٍ مرقَّمٍ جديد؛ واختباراتُ التباين وحارسُ الألوان في بايثون تمرّ.",
        "done",
        100,
        _d(15),
        _d(16),
        "#1447 اندمج 2026-11-15 و#1449 اندمج 2026-11-16؛ اعتمدهما المالكُ على 8500",
        "#1447 #1448 #1449",
        "",
        "**بندٌ جديد.** #1447 مرحلةُ الألوان (أنماطُ الأساس والسمات ومرآتُها في core.brand ومرجعُ الهويّة المولَّد). "
        "#1449 مرحلةُ الشعار: القفلُ الأبيضُ على العنّابيّ بلا شريحةٍ في الترويسة (40) والدخول (80) وصفحة الخطأ (80)، "
        "وأيقوناتُ static/icons/v6 من الرمز الكامل (المعتمةُ بنسبة 0.38، وفافكون يبيضّ على التبويب الداكن)، "
        "ورفعُ ذاكرتَي عاملَي الخدمة إلى v9. #1448 إصلاحُ CI مصاحب (تثبيتُ ubuntu-24.04 في وظائف postgres). "
        "**المقيس (2026-11-16، curl):** نقطةُ الصحّة على الإنتاج تُظهر إيداعَ #1449، وfavicon.svg في v6 والقفلُ الأبيضُ يُخدمان بـ200. "
        "**لم يُقَس** ظهورُها على أجهزة المستخدمين ولا تحديثُ أيقونة تطبيقٍ مثبَّتٍ من قبل.",
        904,
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
        criterion,
        status,
        progress,
        start,
        end,
        basis,
        prs,
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
            effort=1.0,
            deps="",
            criterion=criterion,
            gate="",
            pr=prs,
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
        ("roadmap", "0085_sync_items_2026_10_26"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
