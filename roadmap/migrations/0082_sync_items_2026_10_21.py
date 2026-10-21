"""الخارطةُ السادسةُ والستّون (2026-10-21): دمجُ #1178 (بندٌ جديد N-152) و#1211 (ملاحظةٌ على N-098).

حارسةٌ كسابقاتها: لا يُنشأ بندٌ موجود، ولا ملاحظةَ تتكرّر، ولا حالةَ أو تقدّمَ لبندٍ قائمٍ يُلمس.
**المقيس:** الإيداعان في main (فحصُ git)؛ لم أقِس الإنتاجَ ولا الاستعمالَ الفعليّ. لا هجرةَ ولا صلاحيةَ في الطلبين.
**المستودعُ عامّ:** نصوصٌ محايدةٌ بلا أسماءٍ ولا مفاتيح.
"""

import datetime

from django.db import migrations

STAMP = "[2026-10-21]"
DAY = datetime.date(2026, 10, 20)

# (الرمز، المصدر، المسار، العنوان، الاعتماديّات، المعيار، الحالة، التقدّم، البداية، النهاية،
# أساسُ التاريخ، الجهد، البوّابة، الطلب، المرجع، الملاحظة، ترتيبُ الفرز)
NEW_ITEMS = [
    (
        "N-152",
        "N",
        "behavior",
        "توحيدُ شاشتَي تسجيل المخالفة في شاشةٍ واحدة",
        "",
        "موضعُ التسجيل واحدٌ لكلّ دورٍ يملك قدرةَ التسجيل، والمسارُ القديمُ يحوّل إليه؛ اختبارٌ يثبّت التحويلَ.",
        "done",
        100,
        DAY,
        DAY,
        "#1178 اندمج 2026-10-20 (الإيداع d89158e4)",
        1.0,
        "",
        "#1178",
        "W-20261001-042",
        "**بندٌ جديد.** حُذف قالبُ التسجيل السريع وصار تحويلاً دائماً إلى نموذج التقرير الكامل. **المقيس:** الإيداعُ في main. "
        "لم يُقَس أثرُه على الاستعمال الفعليّ.",
        886,
    ),
]

NOTES = [
    (
        "N-098",
        "#1211",
        "اندمج #1211 (2026-10-21، W-20261009-018): سجلُّ خليّة شبكة الصفّ يلحق تاريخَ الخليّة (?date=). **ما يبقى:** تسويةُ الإدخالات "
        "المعلَّقة. **لم يُقَس** أثرُه على الاستعمال الفعليّ. لا تغيّرَ في الحالة أو التقدّم.",
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
        ("roadmap", "0081_clinic_family_2026_10_20"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
