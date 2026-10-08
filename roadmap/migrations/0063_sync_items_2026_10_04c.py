"""الخارطةُ التاسعةُ والأربعون (2026-10-04): نشرُ #848 (لوحات الأدوار) و#851 (ضبطُ نطاق البحث السريع عن الطلبة)، وبندُ N-091.

حارسةٌ كسابقاتها: لا يُلمس بندٌ إلّا إن طابقت حالتُه وتقدّمُه آخرَ لقطة، ولا تُكرَّر ملاحظةٌ، ولا يُنشأ بندٌ موجود.

**N-085:** يتقدّم اشتقاقاً بنشر #848 ولا يُغلق (يبقى دَينٌ مسمّى P3).
**N-091 (#851):** منشورٌ بالدفتر؛ تغييرُ صلاحيّةٍ بقرار المالك D-192م المسجَّل في decisions.md (لا أعدّه تأكيداً مباشراً لهذه الجلسة).
**المستودعُ عامّ:** نصوصٌ محايدةٌ بلا تفاصيل ثغراتٍ ولا تسميةِ أدوارٍ ولا بياناتٍ شخصيّة.
"""

import datetime

from django.db import migrations

STAMP = "[2026-10-04]"
D = datetime.date
DAY = D(2026, 10, 4)

# (الرمز، (الحالة، التقدّم) المتوقَّعان، الحالة الجديدة، التقدّم الجديد، رمزُ طلبٍ يُضاف، سطر الملاحظة)
UPDATES = [
    (
        "N-085",
        ("doing", 40),
        "doing",
        55,
        "#848",
        "**#848 نُشر (الدفتر: W-20261003-030 published بالإنتاج edfb66d؛ تأكيدُ جلسة النشر):** لوحةُ المدير عدّادٌ ورابطٌ بلا أسماء طلبة (D-171م)، وعدّاداتُ get_admin_ops_ctx بقدرة وجهتها، وقدرةٌ جديدة dashboard.absence_alert_names لأسماء تنبيهات الغياب (تغييرُ صلاحيّةٍ بقرار المالك بحسب وصف الطلب)، "
        "وإزالةُ بندَين من الدَّين المسمّى في حارس #829، وسقّاطةُ mypy 15 ← 14. تغييرٌ بصريٌّ مقصودٌ أقرّه المالكُ بحسب وصف الطلب (غيابُ شريط «ما ينتظر الإدارة» عن دورٍ إداريٍّ لا يملك القدرتين). "
        "**المقيس (0404، لا قياسي):** 72 اختباراً ناجحاً وسقّاطةُ mypy 1216 بنسخٍ مثبَّتة؛ **ووصفُ الطلب يذكر** 196 ناجحاً (مجموعةٌ أوسع). "
        "**قياسُ 0702 بعد نشر #848 و#851 على edfb66dd (طابورُ الدمج وpush، CI فقط):** الناجح 11,564، والتغطية 87.79%، وmypy 1,216 (يطابق قياسَ 0404)، وهامشُ CSS 535، ولا انحراف، والبوّابة 14.0–14.6 دقيقة؛ ولقطاتُ main ناجحةٌ بعد التغيير البصريّ المقصود. **ما بقي:** get_specialist_social_ctx وعدّادُ العيادة في get_director_ctx (P3)، فالبندُ لا يُغلق. **التقدّمُ 55% اشتقاقٌ** (من 40%) لا قياس، ولم يُقَس أثرُه على الإنتاج.",
    ),
]

# ملاحظاتٌ على بنودٍ قائمة تُلحق مرّةً واحدة بلا لمس الحالة ولا التقدّم: (الرمز، السطر)
NOTES = [
    (
        "N-090",
        "**تحديث:** البطاقةُ المنفصلة التي كانت بانتظار قرار المالك (W-20261004-005) نُفّذت بالطلب #851 وسُجّلت بنداً N-091؛ أمّا ترشيحٌ آخر فلم يُبدأ بعدُ (بإفادة 0406).",
    ),
]

# بنودٌ جديدة: (الرمز، المصدر، المسار، العنوان، الاعتماديّات، المعيار، الحالة، التقدّم، البداية، النهاية، أساسُ التاريخ، الجهد، البوّابة، طلب الدمج، المرجع، الملاحظة، الترتيب)
NEW_ITEMS = [
    (
        "N-091",
        "N",
        "backend",
        "ضبطُ نطاق صلاحيّة البحث السريع عن الطلبة بقرار المالك (D-192م)",
        "",
        "سحبُ قدرة البحث السريع عن الطلبة صراحةً من أربعة أدوار لا حاجة لها بها في عملها، وبقاءُ الباقين كما كانوا؛ في core/capabilities.py واختباراتٍ tests/test_student_search_capability.py.",
        "done",
        100,
        DAY,
        DAY,
        "W-20261004-005، #851 نُشر edfb66d (2026-10-04، الدفتر)",
        0.5,
        "",
        "#851",
        "",
        "**بندٌ جديدٌ بقاعدة الإدراج (لا بندَ قائمٌ يغطّيه).** تغييرُ صلاحيّةٍ بقرار المالك D-192م المسجَّل في decisions.md (لا أعدّه تأكيداً مباشراً لي)؛ ملفّان (+5 −1 و+68 اختبارات) بلا هجرة. "
        "**المقيس (0406):** tests/test_student_search_capability.py — الأدوارُ الأربعة مردودون وبقيّةُ الطاقم كما كانت وأصحابُ قدرةٍ أخرى مثبَّتون؛ وحكمُ 0105 «لا اعتراض» بإفادة 0406. "
        "**حدُّ القرار:** أدوارٌ أخرى لم تُمسّ؛ وترشيحٌ آخر لم يُبدأ. **لم يُقَس** أثرُه على الإنتاج.",
        819,
    ),
]


def _add_pr(existing, token):
    """تُضيف رمزَ الطلب دون تكرارٍ ودون تجاوز حدّ الحقل 64 (وإلّا يبقى الحقلُ كما هو)."""
    if not token:
        return existing
    joined = " ".join(dict.fromkeys([*existing.split(), *token.split()]))
    return joined if len(joined) <= 64 else existing


def sync(item_model):
    """تُطبِّق تحديثاتِ البنود الحارسة؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, expected, status, progress, pr, line in UPDATES:
        item = item_model.objects.filter(code=code).first()
        if item is None or (item.status, item.progress) != expected or line in item.note:
            continue
        item.status, item.progress = status, progress
        item.pr = _add_pr(item.pr, pr)
        item.note = f"{item.note}\n{STAMP} {line}".strip()
        item.save(update_fields=["status", "progress", "pr", "note", "updated_at"])
        changed.append(code)
    return changed


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
    sync(item_model)
    sync_notes(item_model)
    add_new_items(item_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0062_sync_items_2026_10_04b"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
