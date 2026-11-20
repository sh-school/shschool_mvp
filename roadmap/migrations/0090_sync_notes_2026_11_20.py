"""الخارطة (2026-11-20): ملاحظةٌ على N-169 بما اندمج بعد 0088 — إصلاحُ مسارات 45 بنداً وحارسُها (#1487).

حارسةٌ كسابقاتها: الملاحظةُ لا تتكرّر، ورمزُ الطلب يُضاف دون تكرارٍ ودون تجاوز حدّ الحقل، ولا حالةَ أو تقدّمَ يُلمس.
لا بندَ جديداً: العملُ إصلاحٌ لما كشفه التحقّقُ من N-169 على الإنتاج، فمكانُه ملاحظةٌ على البند نفسه.
**المستودعُ عامّ:** نصوصٌ محايدةٌ بلا أسماءٍ ولا مضيفات.
"""

from django.db import migrations

STAMP = "[2026-11-20]"

# (الرمز، الطلب، الملاحظة) — تُلحق بلا لمس الحالة أو التقدّم
NOTES = [
    (
        "N-169",
        "#1487",
        "اندمج #1487 ونُشر (2026-11-20): لم يظهر البندُ في الصفحة لأن مسارَه كُتب `security` وهو خارج قائمة المسارات، "
        "ومعه 44 بنداً آخر بمساراتٍ مثلِه. نقلتها الهجرة 0089 إلى مساراتٍ معتمدة، وأُضيف حارسٌ يقرأ كلَّ هجرة خارطةٍ بعدها "
        "ويرفض المسارَ الغريب. **المقيس (2026-11-20):** بياناتُ الصفحة على الإنتاج بعد النشر: 547 بنداً، صفرٌ منها بمسارٍ "
        "خارج القائمة (كانت 45)، والبندُ ظاهرٌ في خليّة «أمن وامتثال» بالمرحلة P2. لا تغيّرَ في الحالة أو التقدّم.",
    ),
]


def _add_pr(existing, token):
    """تُضيف رمزَ الطلب دون تكرارٍ ودون تجاوز حدّ الحقل 64 (وإلّا يبقى الحقلُ كما هو)."""
    if not token:
        return existing
    joined = " ".join(dict.fromkeys([*existing.split(), *token.split()]))
    return joined if len(joined) <= 64 else existing


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
        ("roadmap", "0089_fix_item_lanes_2026_11_20"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
