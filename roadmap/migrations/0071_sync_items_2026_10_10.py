"""الخارطةُ السابعةُ والخمسون (2026-10-10): دمجُ #920 وتجربةُ المولّد V2 — ملاحظةٌ واحدةٌ على SCH-22 بلا لمسٍ للحالة والتقدّم.

حارسةٌ كسابقاتها: الملاحظةُ تُلحق مرّةً واحدة، وقاعدةٌ بلا استيرادٍ لا تتغيّر.

**ما دخل:** #920 (W-20261009-030): HC11 بالساعة في نموذج V2 (مدموج). وتجربةُ المولّد على الإنتاج: مسوّدةٌ غيرُ منشورة.
**ما لم يدخل:** نشرٌ أو اعتمادٌ؛ فالمرحلةُ التالية مراجعةٌ واعتمادٌ بقرار المالك.
**المستودعُ عامّ:** نصوصٌ محايدةٌ بلا بياناتٍ شخصيّةٍ ولا تفاصيلِ ثغرات.
"""

import datetime

from django.db import migrations

STAMP = "[2026-10-10]"

NOTES = [
    (
        "SCH-22",
        "#920",
        "اندمج #920 (2026-10-09، W-20261009-030) في V2 بلا هجرة: قيدُ HC11 بالساعة في نموذج CP-SAT يطابق المُقيِّم (موارد same_level_only، "
        "وتقاطعٌ يزيد على 5 دقائق) مع اختبارات؛ وهو الإصلاحُ الثاني بعد #914. وبإبلاغ المايسترو جُرّب المولّدُ بعده على الإنتاج: "
        "توليدٌ واحدٌ **مسوّدةٌ غيرُ منشورة** (حصصه 871، مخالفاتُه الصلبة 0، قيمةُ الهدف 10,855)؛ والأرقامُ بإبلاغ الجلسة المنفِّذة ولم يقسها "
        "الرصدُ بأداته. **ما يبقى:** مراجعةُ المسوّدة واعتمادُها قبل النشر بقرار المالك؛ ولا يُقال «منشور» أو «معتمد». "
        "لا تغيّرَ في الحالة أو التقدّم.",
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
        ("roadmap", "0070_sync_items_2026_10_09c"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
