"""الخارطة (2026-11-27): تسجيلُ البند U-11 «جزئيًّا» بعد نشر المرحلة 1 (طلب #1527).

حارسةٌ على نمط 0095: لا يُعدَّل البندُ إلا إن طابقت حالتُه وتقدُّمه المتوقَّعَين ولم تكن الملاحظةُ مكتوبةً فيه.
لا تنفيذَ لأيّ بند، ولا يُغيَّر gate ولا تاريخٌ ولا عنوانٌ ولا معيارٌ ولا مؤشّر، ولا يُنشأ بند.
**المستودعُ عامّ:** لا تفاصيلَ غير ما في نصّ الملاحظة.
"""

from typing import Any

from django.db import migrations

STAMP = "[2026-11-27]"

CODE = "U-11"
OLD_STATUS = "todo"
OLD_PROGRESS = 10
NEW_STATUS = "doing"
NEW_PROGRESS = 60
PR = "#1527"
NOTE = (
    "المرحلة 1 منشورة: المحو يجهّل السجل الأكاديمي ولا يحذفه. "
    "يبقى التوقيع المزدوج (المدير ومسؤول حماية البيانات)."
)


def _add_pr(existing: str, token: str) -> str:
    """تُضيف رقمَ الطلب دون تكرارٍ ودون تجاوز حدّ الحقل 64 (وإلّا يبقى الحقلُ كما هو)."""
    joined = " ".join(dict.fromkeys([*existing.split(), *token.split()]))
    return joined if len(joined) <= 64 else existing


def sync(item_model: Any) -> bool:
    """تُطبّق التسجيلَ على U-11 إن كان في حالته المتوقَّعة؛ تُرجع True إن تغيّر البند."""
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
        ("roadmap", "0095_sync_owner_decisions_2026_11_27"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
