"""الخارطة (2026-11-27): تسجيلُ قرارات المالك على بنود الخارطة (إغلاقان، تأجيلات، ملاحظات).

حارسةٌ كسابقاتها: لا يُعدَّل بندٌ إلا إن طابقت حالتُه وتقدُّمه المتوقَّعَ ولم يكن السطرُ في ملاحظته.
لا تنفيذَ لأيّ بند، ولا يُغيَّر gate ولا تاريخٌ ولا عنوانٌ ولا معيارٌ ولا مؤشّر ولا جدولُ القرارات، ولا يُنشأ بند.
**المستودعُ عامّ:** لا تفاصيلَ غير ما في سطور الجدول.
"""

from typing import Any

from django.db import migrations

STAMP = "[2026-11-27]"

# كلُّ بندٍ في سطر: الرمز | المتوقَّع (حالة/تقدّم) | الحالة الجديدة | التقدّم | الطلب | سطر الملاحظة
_TABLE = """
MAE-02 | doing/50 | deferred | 50 |  | قرار المالك: يؤجَّل؛ أُلغي نظام الجلسات.
MAE-04 | doing/10 | deferred | 10 |  | قرار المالك: يؤجَّل؛ أُلغي نظام الجلسات.
MAE-06 | doing/10 | deferred | 10 |  | قرار المالك: يؤجَّل.
MAE-13 | todo/0 | deferred | 0 |  | قرار المالك: يُضمّ إلى REP-09.
DBT-48 | todo/0 | deferred | 0 |  | قرار المالك: يؤجَّل؛ يُعاد فتحه إن ظل البطء يعطّل المشغّل.
DBT-52 | todo/0 | deferred | 0 |  | قرار المالك: يؤجَّل؛ يُعاد فتحه إن عادت المشكلة.
SCH-09 | todo/0 | deferred | 0 |  | قرار المالك: يؤجَّل؛ المحسّن القديم لم يعد المسار المستعمل.
SCH-11 | doing/15 | deferred | 15 |  | قرار المالك: يؤجَّل؛ المدرسة تعمل على جدول aSc.
SCH-12 | todo/0 | deferred | 0 |  | قرار المالك: يؤجَّل مع بنود التوليد.
VI-55 | todo/0 | deferred | 0 |  | قرار المالك: يُضمّ إلى N-084.
VI-56 | todo/0 | deferred | 0 |  | قرار المالك: يؤجَّل؛ زال دافعه. يُفتح إن ضاق الهامش.
N-141 | doing/90 | deferred | 90 |  | قرار المالك: يؤجَّل.
PRP-02 | todo/0 | deferred | 0 |  | قرار المالك: يؤجَّل.
OWN-31 | todo/0 | deferred | 0 |  | قرار المالك: يؤجَّل؛ يُراجَع قبل إعداد جدول العام التالي.
REP-12 | todo/0 | deferred | 0 |  | قرار المالك: يبقى مؤجَّلاً.
VI-18 | todo/0 | deferred | 0 |  | قرار المالك: اعتُمد ADR-0006 (لا استعلامات حاويات)؛ يؤجَّل لأن المعيار لن يُنفَّذ.
QCC-05 | doing/0 | done | 100 | #702 | قرار المالك: يُغلق بتعديل المعيار: سقف الإشعارات 12 يومياً مقبول، وحلّ التشغيل الحيّ محل وضع الظل.
N-143 | doing/90 | done | 100 | #1068 | قرار المالك: لا رصد للمعلّم بعد 14:00؛ يُغلق. النافذة المركزية قائمة.
SCH-06 | deferred/80 | deferred | 80 |  | قرار المالك: يبقى مؤجَّلاً؛ تجاوزه استيراد aSc.
N-099 | doing/50 | doing | 50 |  | قرار المالك: يبقى، ويُحصر في التحقق من إخطار الغياب وعتباته.
U-03 | todo/0 | todo | 0 |  | فاتت نافذته المحددة؛ قرار المالك: تُحدَّد نافذة جديدة لاحقاً.
U-04 | doing/50 | doing | 50 |  | قرار المالك: سيملأ فراغات الإشعار.
U-32 | deferred/0 | deferred | 0 |  | قرار المالك: يبقى مؤجَّلاً ويُراجَع أول الفصل الدراسي الثاني.
CLN-05 | todo/0 | todo | 0 |  | قرار المالك: يشغّلها بنفسه.
LAY-07 | todo/0 | todo | 0 |  | قرار المالك: تُعاد جدولة الجولتين.
OWN-08 | todo/0 | todo | 0 |  | قرار المالك: يُستخرج النص من الدليل لاحقاً ثم يؤكده.
N-042 | doing/83 | doing | 83 |  | 2026-11-27: لا مشكلة غير محلولة بهذا الخطأ في Sentry خلال 90 يوماً؛ يبقى تصدير حقيقي من الإنتاج.
"""


def rows() -> list[tuple[str, str, int, str, int, str, str]]:
    """(الرمز، الحالة المتوقَّعة، تقدّمها، الحالة الجديدة، تقدّمها، الطلب، الملاحظة) لكلّ سطر."""
    parsed = []
    for line in _TABLE.strip().splitlines():
        code, expected, status, progress, pr, note = (c.strip() for c in line.split("|"))
        old_status, old_progress = expected.split("/")
        parsed.append((code, old_status, int(old_progress), status, int(progress), pr, note))
    return parsed


def _add_pr(existing: str, token: str) -> str:
    """تُضيف رقمَ الطلب دون تكرارٍ ودون تجاوز حدّ الحقل 64 (وإلّا يبقى الحقلُ كما هو)."""
    joined = " ".join(dict.fromkeys([*existing.split(), *token.split()]))
    return joined if len(joined) <= 64 else existing


def sync(item_model: Any) -> list[str]:
    """تُطبّق الجدولَ على ما لم يمسّه أحدٌ من البنود القائمة؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, old_status, old_progress, status, progress, pr, note in rows():
        item = item_model.objects.filter(
            code=code, status=old_status, progress=old_progress
        ).first()
        if item is None or note in item.note:
            continue
        item.status = status
        item.progress = progress
        item.note = f"{item.note}\n{STAMP} {note}".strip()
        item.pr = _add_pr(item.pr, pr)
        item.save(update_fields=["status", "progress", "note", "pr", "updated_at"])
        changed.append(code)
    return changed


def forwards(apps: Any, schema_editor: Any) -> None:
    item_model = apps.get_model("roadmap", "RoadmapItem")
    # قاعدةٌ بلا استيراد (اختبار، شجرةٌ جديدة): لا شيء يُزامَن.
    if not item_model.objects.exists():
        return
    sync(item_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0094_sync_verification_2026_11_26"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
