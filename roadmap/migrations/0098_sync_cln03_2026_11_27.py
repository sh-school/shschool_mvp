"""الخارطة (2026-11-27): تسجيلُ البند CLN-03 «جزئيًّا» بعد سدّ تبويب العيادة في ملف الطالب وواجهة الزيارات (طلب #1531).

حارسةٌ على نمط 0097: لا يُعدَّل البندُ إلا إن طابقت حالتُه وتقدُّمه المتوقَّعَين ولم تكن الملاحظةُ مكتوبةً فيه.
لا تنفيذَ لأيّ بند، ولا يُغيَّر gate ولا تاريخٌ ولا عنوانٌ ولا معيارٌ ولا مؤشّر، ولا يُنشأ بند.
**المستودعُ عامّ:** لا تفاصيلَ غير ما في نصّ الملاحظة.
"""

from typing import Any

from django.db import migrations

STAMP = "[2026-11-27]"

CODE = "CLN-03"
OLD_STATUS = "doing"
OLD_PROGRESS = 0
NEW_STATUS = "doing"
NEW_PROGRESS = 30
PR = "#1531"
NOTE = "جزئي: سُدّ تبويب العيادة في ملف الطالب وواجهة الزيارات، ويبقى غيرهما. قرار المالك: لا تُعفى شاشات التشغيل من التدقيق."


def _add_pr(existing: str, token: str) -> str:
    """تُضيف رقمَ الطلب دون تكرارٍ ودون تجاوز حدّ الحقل 64 (وإلّا يبقى الحقلُ كما هو)."""
    joined = " ".join(dict.fromkeys([*existing.split(), *token.split()]))
    return joined if len(joined) <= 64 else existing


def sync(item_model: Any) -> bool:
    """تُطبّق التسجيلَ على CLN-03 إن كان في حالته المتوقَّعة؛ تُرجع True إن تغيّر البند."""
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
        ("roadmap", "0097_sync_u09_2026_11_27"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
