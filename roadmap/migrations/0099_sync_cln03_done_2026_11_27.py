"""الخارطة (2026-11-27): تسجيلُ البند CLN-03 «منجزًا» بعد تدقيق فتح البيانات الصحية وشاشات التشغيل (طلب المالك 2026-11-27).

حارسةٌ على نمط 0097: لا يُعدَّل البندُ إلا إن طابقت حالتُه وتقدُّمه المتوقَّعَين ولم تكن الملاحظةُ مكتوبةً فيه.
لا تنفيذَ لأيّ بند، ولا يُغيَّر gate ولا تاريخٌ ولا عنوانٌ ولا معيارٌ ولا مؤشّر، ولا يُنشأ بند.
**المستودعُ عامّ:** لا تفاصيلَ غير ما في نصّ الملاحظة.
"""

from typing import Any

from django.db import migrations

STAMP = "[2026-11-27]"

CODE = "CLN-03"
OLD_STATUS = "doing"
OLD_PROGRESS = 30
NEW_STATUS = "done"
NEW_PROGRESS = 100
# أرقامُ الطلبات المدمجة في البند؛ تُضاف دون تكرارٍ إلى ما هو موجود.
PRS = ("#1532", "#1534", "#1535", "#1536", "#1537", "#1538", "#1539")
NOTE = (
    "منجز: يسجَّل في التدقيق فتح البيانات الصحية في شاشات المنصة وطباعتها وواجهاتها ولوحة الإدارة، "
    "وشاشات التشغيل المتكررة بالدمج اليومي بالطالب."
)


def _add_prs(existing: str, tokens: tuple[str, ...]) -> str:
    """تُضيف أرقامَ الطلبات دون تكرارٍ ودون تجاوز حدّ الحقل 64 (وإلّا يبقى الحقلُ كما هو)."""
    joined = " ".join(dict.fromkeys([*existing.split(), *tokens]))
    return joined if len(joined) <= 64 else existing


def sync(item_model: Any) -> bool:
    """تُطبّق التسجيلَ على CLN-03 إن كان في حالته المتوقَّعة؛ تُرجع True إن تغيّر البند."""
    item = item_model.objects.filter(code=CODE, status=OLD_STATUS, progress=OLD_PROGRESS).first()
    if item is None or NOTE in item.note:
        return False
    item.status = NEW_STATUS
    item.progress = NEW_PROGRESS
    item.note = f"{item.note}\n{STAMP} {NOTE}".strip()
    item.pr = _add_prs(item.pr, PRS)
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
        ("roadmap", "0098_sync_cln03_2026_11_27"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
