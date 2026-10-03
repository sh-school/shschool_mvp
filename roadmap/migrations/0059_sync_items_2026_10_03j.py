"""الخارطةُ الخامسةُ والأربعون (2026-10-03): نشرُ #833 (N-087 يتقدّم ولا يُغلق)، وقياسُ 0702 بعد نشر #834 على N-086.

حارسةٌ كسابقاتها: لا يُلمس بندٌ إلّا إن طابقت حالتُه وتقدّمُه آخرَ لقطة، ولا تُكرَّر ملاحظةٌ.

**N-087 (#833):** نُشر بتأكيد جلسة النشر؛ لكنّ البذرَ الحيّ على 8500 لم يُقَس (تتحقّق منه 0501) فيبقى doing لا done.
**N-086:** قياسُ CI فقط بعد النشر، لا أثرَ إنتاج.

والمستودعُ عامّ: نصوصٌ محايدة بلا تفاصيل ثغراتٍ ولا بياناتٍ شخصيّة.
"""

import datetime

from django.db import migrations

STAMP = "[2026-10-03]"
D = datetime.date
DAY = D(2026, 10, 3)

# (الرمز، (الحالة، التقدّم) المتوقَّعان، الحالة الجديدة، التقدّم الجديد، رمزُ طلبٍ يُضاف، سطر الملاحظة)
UPDATES = [
    (
        "N-087",
        ("doing", 80),
        "doing",
        90,
        "",
        "**#833 نُشر fb0c935 (تأكيدُ جلسة النشر؛ الدفتر: W-20261003-023 published):** مصيدةُ المصادقة في الإنتاج بالوسم المركَّب، واستثناءُ حقن 8500←الإنتاج بقائمة سماح، وأمرُ preview_accounts، وبذرُ الإقلاع في compose المعاينة وحدَه. "
        "**المقيس (0406):** اختباراتُ tests/test_preview_accounts.py (48 فأكثر) خضراء، وشروطُ 0105 الأحد عشر، والتخفيفُ مسجَّلٌ في regression_guards.md. "
        "**لم يُقَس** البذرُ الحيّ على 8500 (تتحقّق منه 0501 بعد التثبيت المؤقّت) فلا done؛ والتقدّمُ 90% اشتقاقٌ لا قياس.",
    ),
]

# ملاحظاتٌ على بنودٍ قائمة تُلحق مرّةً واحدة بلا لمس الحالة ولا التقدّم: (الرمز، السطر)
NOTES = [
    (
        "N-086",
        "**قياسُ 0702 بعد نشر #834 على a9d1c175 (طابورُ الدمج فقط، لا أثرَ إنتاج):** الناجحُ في الشظايا 11,336، والتغطيةُ المدموجة 87.85%، وmypy 1,217 في 121 ملفاً، وهامشُ CSS 535 بايتاً، وسقّاطةُ الطبقات بلا مخالفة، ولا انحراف. "
        "وزمنُ البوّابة 18.7 دقيقة (أطولُ من 14.75 في قياسٍ سابق، **والسببُ غيرُ معروف** ولا أنسبه إلى #834).",
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


def forwards(apps, schema_editor):
    item_model = apps.get_model("roadmap", "RoadmapItem")
    # قاعدةٌ بلا استيراد (اختبار، شجرةٌ جديدة): لا شيء يُزامَن.
    if not item_model.objects.exists():
        return
    sync(item_model)
    sync_notes(item_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0058_sync_items_2026_10_03i"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
