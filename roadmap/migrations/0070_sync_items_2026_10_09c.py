"""الخارطةُ السادسةُ والخمسون (2026-10-09): دمجُ #913 — ملاحظةُ تقدّمٍ على N-098 بلا بندٍ جديد ولا لمسٍ للحالة.

حارسةٌ كسابقاتها: لا حالةَ أو تقدّمَ لبندٍ قائمٍ يُلمس، والملاحظةُ تُلحق مرّةً واحدة، وقاعدةٌ بلا استيرادٍ لا تتغيّر.

**ما دخل:** #913 (W-20261009-003): حذفُ الشبكة القديمة وكلِّ كود الاعتماد؛ جدولُ الشعبة العموديّ واجهةُ الرصد الوحيدة.
**المستودعُ عامّ:** نصوصٌ محايدةٌ بلا بياناتٍ شخصيّةٍ ولا تفاصيلِ ثغرات.
"""

import datetime

from django.db import migrations

STAMP = "[2026-10-09]"

NOTES = [
    (
        "N-098",
        "#913",
        "اندمج #913 (2026-10-09، W-20261009-003): حُذفت كشوفُ الحصّة القديمة وصفحاتُ الاعتماد والتثبيت والتأخّر والتراجع وقوالبُها "
        "وكلُّ كود الاعتماد، فصار جدولُ الشعبة العموديّ واجهةَ الرصد الوحيدةَ لكلّ الأدوار وكلّ التواريخ (أمرُ المالك). الرصدُ نهائيٌّ "
        "فوريّ لكلّ المعلّمين، والتصحيحُ بسببٍ لحامل الجناح والقيادة، والمستقبلُ للقراءة فقط. أُبقيت جداولُ السجلّ وسلسلةُ S3 للإدخالات "
        "المعلَّقة وبلاطةُ «رصدٌ معلّق» إلى حين التسوية (قرارُ المالك، W-20261008-020). **ما يبقى:** تاريخُ السجلّ (W-20261009-018، مؤجَّل) "
        "وتسويةُ الإدخالات المعلَّقة. **لم يُقَس** أثرُه على الاستعمال الفعليّ. لا تغيّرَ في الحالة أو التقدّم.",
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
    sync_notes(item_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0069_sync_items_2026_10_09b"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
