"""الخارطةُ الحاديةُ والأربعون (2026-10-03): نشرُ #818، وبندان جديدان لعملٍ دُمج بلا بند (#820 منشورٌ، #819 مدموجٌ بلا نشر)، وتسجيلُ #822 في مواصفة V2.

حارسةٌ كسابقاتها: لا تُكرَّر ملاحظةٌ، ولا يُنشأ بندٌ موجود، ولا بندَ يُغلق بلا قياسٍ أو نشرٍ مؤكَّد.

**N-082 (#820):** منشورٌ بتأكيد جلسة النشر؛ الإيداعُ الثاني #823 لم يُدمج بعدُ فالبندُ doing.
**N-083 (#819):** منشورٌ بحسب الدفتر وتأكيدِ جلسة النشر → doing لا done؛ هو الإيداعُ الأوّل من عدّةِ إيداعات.
**SCH-22 (#822):** وثائقُ فقط (مواصفة القيود)؛ قرارُ D-166م مسجَّلٌ في decisions.md ولا يُعدّ تأكيداً مباشراً لهذه الجلسة، ولا يتغيّر التقدّم.

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
        "QCC-10",
        "**#818 نُشر (تأكيدُ جلسة النشر: الإنتاجُ على bacfa0d):** تعطيلُ الجمع الكسول داخل اختبار صفحة الحالة لفشلٍ متقطّعٍ يُسقط pytest تحت xdist. "
        "**لم يُقَس** بعد النشر أنّ الفشل المتقطّع لا يعود؛ والمراحلُ التالية ما زالت محجوبةً بقرار المالك.",
    ),
    (
        "SCH-22",
        "**#822 نُشر (الدفتر: published بتاريخ 2026-10-03، الإنتاج 0959399؛ وثائقُ فقط):** مواصفةُ القيود (docs/schedule_v2/constraints_spec.html) تسجّل قرارَ D-166م (مسجَّلٌ في decisions.md: "
        "أولى ≤ 2 وأخيرة ≤ 2 لكلّ معلّم) ورمزَ سقف الأولى HC22 ومسردَ رموز القيود. لا شيفرةَ ولا هجرة ولا قياس، فالتقدّمُ كما هو.",
    ),
]

# بنودٌ جديدة: (الرمز، المصدر، المسار، العنوان، الاعتماديّات، المعيار، الحالة، التقدّم، البداية، النهاية، أساسُ التاريخ، الجهد، البوّابة، طلب الدمج، المرجع، الملاحظة، الترتيب)
NEW_ITEMS = [
    (
        "N-082",
        "N",
        "frontend",
        "صفحةُ المنع 403: زرُّ «تسجيل الخروج» لكلّ مستخدمٍ مصادَق",
        "",
        "زرُّ خروجٍ (form POST مع csrf) في صفحة المنع لكلّ مستخدمٍ مصادَق بجانب زرّي العودة، ولا يظهر لزائرٍ لم يدخل؛ **ثمّ** الإيداعُ الثاني (default_landing، #823) لتوجيه المستخدم إلى صفحةٍ يملك صلاحيتها.",
        "doing",
        50,
        DAY,
        None,
        "W-20261003-024 (P1)، #820 نُشر bea8c27 (2026-10-03، تأكيدُ جلسة النشر)",
        1.0,
        "",
        "#820",
        "",
        "**بندٌ جديدٌ بقاعدة الإدراج (لا بندَ قائمٌ يغطّيه).** قوالبُ فقط (403.html وerrors/forbidden.html وerrors/_error_page.html) بمعامل show_logout؛ بلا بايثون ولا هجرة ولا صلاحيّات. "
        "**المقيس (0404):** اختباراتُ test_forbidden_logout الستّةُ ناجحة. **لم يُقَس** أثرُه على الإنتاج. "
        "الإيداعُ الثاني #823 (الرأس 2cf09c0f بنقل 0404) أخضرُ ولم يُدمج بعدُ، فلا done؛ والتقدّمُ 50% اشتقاقٌ (إيداعٌ من اثنين) لا قياس.",
        810,
    ),
    (
        "N-083",
        "N",
        "backend",
        "امتثالُ حماية البيانات: ملتقِطاتُ core/signals.py تكتب معرّفاً مقنَّعاً لا اسماً شخصيّاً في سجلّ التدقيق",
        "",
        "ملتقِطاتُ الإشارات لا تكتب اسماً شخصيّاً في AuditLog.object_repr بل معرّفاً مقنَّعاً؛ **ثمّ** الإيداعاتُ اللاحقة (الطلبة والكادر وحارسُ AST) رؤوسٌ منفصلة.",
        "doing",
        25,
        DAY,
        None,
        "W-20261003-019 (الإيداع 1)، نُشر 07113af (2026-10-03، تأكيدُ جلسة النشر)",
        2.0,
        "",
        "#819",
        "",
        "**بندٌ جديدٌ بقاعدة الإدراج.** دالّةُ تمثيلٍ مقنَّع في core/audit_repr.py تستعملها الملتقِطات؛ اختبارٌ جديد test_auditlog_no_names_from_signals؛ بلا هجرة. "
        "**بحسب وصف الطلب (مصدرُه جلسةُ التنفيذ لا قياسي):** prepush وlayering وmypy ratchet مرّت محلّيّاً. "
        "**قياسُ 0702 بعد النشر على 07113af3: لا انحرافَ في المؤشّرات** (تغطية 87.84%، اختبارات 11,197 ناجحة، mypy 1,217، اللقطاتُ ناجحة)؛ ولم يُقَس أثرٌ على الإنتاج؛ التقدّمُ 25% اشتقاقٌ (إيداعٌ أوّلُ من عدّةِ إيداعات) لا قياس.",
        811,
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
        ("roadmap", "0054_sync_items_2026_10_03e"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
