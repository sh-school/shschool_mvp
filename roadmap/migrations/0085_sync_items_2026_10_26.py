"""الخارطةُ التاسعةُ والستّون (2026-10-26): ما اندمج بعد 0084 (W-20261023-017) — بندان جديدان وملاحظةٌ على N-164.

حارسةٌ كسابقاتها: لا يُنشأ بندٌ موجود، ولا ملاحظةَ تتكرّر، ولا حالةَ أو تقدّمَ لبندٍ قائمٍ يُلمس.
**المقيس:** الإيداعات في main (فحصُ git)؛ لم أقِس الإنتاجَ ولا الاستعمالَ الفعليّ. لا هجرةَ بنيويّةً ولا صلاحيةَ في هذه الهجرة.
**المستودعُ عامّ:** نصوصٌ محايدةٌ بلا أسماءٍ ولا مفاتيح.
"""

import datetime

from django.db import migrations

STAMP = "[2026-10-26]"
MEASURED = "**المقيس:** الإيداعاتُ في main. لم يُقَس أثرُها على الاستعمال الفعليّ."


def _d(day):
    return datetime.date(2026, 10, day)


# (الرمز، المسار، العنوان، المعيار، الحالة، التقدّم، البداية، النهاية، أساسُ التاريخ، الطلبات، المراجع، الملاحظة، ترتيبُ الفرز)
NEW_ITEMS = [
    (
        "N-167",
        "operations",
        "اختبارُ حملٍ بـLocust لقراءة الحضور والدرجات بحدود قبولٍ p95 وحارسِ مضيفٍ بعيد",
        "سيناريوهاتٌ قراءةً فقط بحدود p95 ونسبةِ أخطاءٍ موثَّقة، ولا تُشغَّل على مضيفٍ بعيدٍ بلا إذنٍ صريح.",
        "doing",
        70,
        _d(25),
        _d(25),
        "#1276 اندمج 2026-10-25",
        "#1276",
        "W-20261025-012",
        "**بندٌ جديد.** سيناريوهان (الحضور والدرجات) قراءةً فقط، وحارسُ المضيف البعيد، وتسجيلُ دخولٍ مرّةً لكلّ تشغيل، ومهارةُ schoolos-load-test. "
        "**لم يُقَس** حملٌ فعليٌّ بعد ولا دُوّنت نتيجةُ تشغيلٍ في README؛ لذا لا يُغلق البند.",
        902,
    ),
    (
        "N-168",
        "operations",
        "تخفيفُ حقن بدء جلسات المنصّة: اختصارُ CLAUDE.md وflow.md ومنعُ أداة Artifact وحذفُ استيراد flow.md وتقصيرُ أوصاف المهارات",
        "أوّلُ ردٍّ بعد البدء أقلُّ من 50,000 رمز بلا إسقاط قاعدةٍ حاكمة.",
        "doing",
        80,
        _d(26),
        _d(26),
        "ثلاثةُ طلباتٍ اندمجت 2026-10-26",
        "#1282 #1283 #1286",
        "W-20261025-030 W-20261026-004 W-20261025-004",
        "**بندٌ جديد.** #1282 اختصارُ CLAUDE.md وflow.md ونقلُ التعليل إلى flow_details.md بلا إسقاط قاعدة؛ و#1283 permissions.deny يضمّ Artifact "
        "وحذفُ سطر استيراد flow.md من CLAUDE.md (مهارة schoolos-flow تغطّيه)؛ و#1286 تقصيرُ سطر description في سبع مهارات (8872 ← 1195 بايتاً) مع حفظ مشغّلات الاستدعاء. **لم يُقَس** حجمُ أوّل ردٍّ بعد البدء التالي، فيبقى البند مفتوحاً.",
        903,
    ),
]

# (الرمز، الطلب، الملاحظة) — تُلحق بلا لمس الحالة أو التقدّم
NOTES = [
    (
        "N-164",
        "#1275",
        "اندمج #1275 (2026-10-26، W-20261025-022): ربطُ منفذ Redis 6380 بـ127.0.0.1 في docker-compose.yml كالمنفذين 8000 و5433. "
        "**لم يُقَس** الاستماعُ المحلّيّ فعلاً بعد إعادة الحاويات (docker ps). لا تغيّرَ في الحالة أو التقدّم.",
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
            src="N",
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
        ("roadmap", "0084_sync_items_2026_10_25"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
