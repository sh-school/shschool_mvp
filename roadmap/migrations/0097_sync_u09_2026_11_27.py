"""الخارطة (2026-11-27): تسجيلُ البند U-09 «منجزًا» بعد نشر القنوات الخارجية لولي الأمر (طلب #1529).

حارسةٌ على نمط 0096: لا يُعدَّل البندُ إلا إن طابقت حالتُه وتقدُّمه المتوقَّعَين ولم تكن الملاحظةُ مكتوبةً فيه.
لا تنفيذَ لأيّ بند، ولا يُغيَّر gate ولا تاريخٌ ولا عنوانٌ ولا معيارٌ ولا مؤشّر، ولا يُنشأ بند.
**المستودعُ عامّ:** لا تفاصيلَ غير ما في نصّ الملاحظة.
"""

from typing import Any

from django.db import migrations

STAMP = "[2026-11-27]"

CODE = "U-09"
OLD_STATUS = "todo"
OLD_PROGRESS = 0
NEW_STATUS = "done"
NEW_PROGRESS = 100
PR = "#1529"
NOTE = "منشور: القنوات الخارجية لولي الأمر بنص محايد، والتفاصيل داخل المنصّة."


def _add_pr(existing: str, token: str) -> str:
    """تُضيف رقمَ الطلب دون تكرارٍ ودون تجاوز حدّ الحقل 64 (وإلّا يبقى الحقلُ كما هو)."""
    joined = " ".join(dict.fromkeys([*existing.split(), *token.split()]))
    return joined if len(joined) <= 64 else existing


def sync(item_model: Any) -> bool:
    """تُطبّق التسجيلَ على U-09 إن كان في حالته المتوقَّعة؛ تُرجع True إن تغيّر البند."""
    item = item_model.objects.filter(code=CODE, status=OLD_STATUS, progress=OLD_PROGRESS).first()
    if item is None or NOTE in item.note:
        return False
    item.status = NEW_STATUS
    item.progress = NEW_PROGRESS
    item.note = f"{item.note}\n{STAMP} {NOTE}".strip()
    item.pr = _add_pr(item.pr, PR)
    item.save(update_fields=["status", "progress", "note", "pr", "updated_at"])
    return True


def forwards(apps: Any, schema_editor: Any) -> None:
    item_model = apps.get_model("roadmap", "RoadmapItem")
    # قاعدةٌ بلا استيراد (اختبار، شجرةٌ جديدة): لا شيء يُزامَن.
    if not item_model.objects.exists():
        return
    sync(item_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0096_sync_u11_2026_11_27"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
