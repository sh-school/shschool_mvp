"""الخارطةُ الثانيةُ والأربعون (2026-10-03): إغلاقُ N-082 بنشر #820 و#823، وملاحظتا #824 (استمارة الزيارة PDF) و#797 (shards pytest).

حارسةٌ كسابقاتها: لا يُلمس بندٌ إلّا إن طابقت حالتُه وتقدّمُه آخرَ لقطة، ولا تُكرَّر ملاحظةٌ.

**N-082 يُغلق** بالطلبين #820 و#823: نشرُهما مؤكَّدٌ مباشرةً من جلسة النشر (الإنتاج على 1c6aac1)؛ وأثرُ الإنتاج لم يُقَس (عند 0105).
**#797:** مدموجٌ ولا تأكيدَ نشرٍ عندي، فملاحظةٌ لا إغلاق.

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
        "N-082",
        ("doing", 50),
        "done",
        100,
        "#823",
        "**أُغلق بنشر الإيداعين:** #820 (زرُّ الخروج في صفحة المنع، نُشر bea8c27) و#823 (default_landing: وجهةٌ بحسب الصلاحيّة، نُشر 1c6aac1) — تأكيدٌ مباشرٌ من جلسة النشر. "
        "**المقيس (0404):** test_default_landing 42 من 42، وحارسُ كلّ الأدوار لم يُسقط دوراً. **لم يُقَس أثرُه على الإنتاج** (تقيسه 0105).",
    ),
]

# ملاحظاتٌ على بنودٍ قائمة تُلحق مرّةً واحدة بلا لمس الحالة ولا التقدّم: (الرمز، السطر)
NOTES = [
    (
        "N-050",
        "**#824 نُشر (الدفتر: W-20261002-016 published، الإنتاج 1c6aac1):** PDF استمارة الزيارة الصفّيّة يطبع الشعبةَ بالرمز المختصر (مثل 11/2) واسمَي الزائر والمُزار بمقطعين. "
        "**المقيس (0408):** لا قياسَ رقميّ؛ دليلُه اختباراتُ الرموز المختصرة في الفرع ولم تُراجَع على CI عنده.",
    ),
    (
        "N-069",
        "**#797 مدموجٌ (2026-10-03، W-20261002-034، الجزء ب):** تقسيمُ pytest في CI على خمسة shards متوازية، وبوّابةُ التغطية تجمع تغطيةَ الـshards ثمّ تطبّق العتبةَ على المدموج. "
        "**المقيس (0408):** جمعُ المجموعة 10106 اختباراً (3028+2364+2622+2087+5)، والمحقِّقُ scripts/ci_shard_verify.py يمرّ. "
        "**لم يُقَس:** زمنُ الدورة على مشغّلات GitHub، ودمجُ التغطية بين مشغّلاتٍ مختلفة؛ ولا تأكيدَ نشرٍ بعد.",
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
        ("roadmap", "0055_sync_items_2026_10_03f"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
