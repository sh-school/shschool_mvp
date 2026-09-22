"""مزامنةُ حالات بنود الخارطة مع ما دُمج ونُشر حتى 2026-09-21.

بياناتُ الخارطة في القاعدة لا في الكود، فلا يمرّ تحديثُها بدفعٍ ودمجٍ إلّا بهجرةِ بيانات.
الهجرةُ **حارسةٌ**: لا تلمس صفّاً إلّا إن كانت حالتُه وتقدّمُه ما كانا في لقطة الاستيراد
(`expect`) — فإن عدّلهما المطوّرُ من الصفحة بعد الاستيراد بقي تعديلُه. تُلحِق سطراً مؤرَّخاً
بالملاحظة ولا تحذف ما فيها. وإن لم يوجد البندُ (قاعدةٌ جديدة) لا تفعل شيئاً.
"""

from django.db import migrations

STAMP = "[2026-09-21]"

# (الرمز، (الحالة، التقدّم) المتوقَّعان، الحالة الجديدة، التقدّم الجديد، سطر الملاحظة، استبدالاتُ العنوان)
UPDATES = [
    (
        "DBT-06",
        ("todo", 0),
        "done",
        100,
        "أُغلق: #461 (django-axes 8.3.1 بجدولٍ مصنَّفٍ وحكم احتفاظ) و#457 (مهلة قراءة redis) مدموجان ومنشوران على الإنتاج.",
        [
            (
                "(#430 يفشل: جدول axes_accessattemptexpiration غير مصنَّف)",
                "(#430 حلّ محلَّه #461: الجدول مصنَّف، منشور)",
            ),
            (
                "والإصلاح في PR #457 (CI أخضر) بانتظار الدمج والنشر بعد الدوام",
                "والإصلاح في PR #457 مدموجٌ ومنشور",
            ),
        ],
    ),
    (
        "U-07",
        ("doing", 50),
        "done",
        100,
        "أُغلق: الحارس البديل #445 مدموج، وهجرة حذف StaffEvaluation (#436) مدموجةٌ ومنشورة (operations.0056).",
        [],
    ),
    (
        "VI-26",
        ("doing", 50),
        "done",
        100,
        "أُغلق: #446 مدموج (أداة القياس + قياسٌ أسبوعيّ في CI).",
        [],
    ),
    (
        "U-30",
        ("doing", 50),
        "doing",
        80,
        "P4-3 مدموج (#448). الباقي D-12 بانتظار المالك.",
        [],
    ),
    (
        "U-41",
        ("doing", 50),
        "doing",
        50,
        "المرحلة 1 مدموجة: #456. المرحلة 2 لم تبدأ.",
        [],
    ),
    (
        "VI-30",
        ("doing", 50),
        "doing",
        50,
        "المرحلة 1 مدموجة: #456.",
        [],
    ),
    (
        "U-04",
        ("doing", 50),
        "doing",
        50,
        "#419 مدموج (تصحيح ادّعاءات إشعار الخصوصيّة).",
        [],
    ),
    (
        "H-03",
        ("doing", 30),
        "doing",
        30,
        "#451 مدموج (81 موضعاً px→rem)؛ بقي رفعُ الصغير إلى 12px.",
        [],
    ),
    (
        "DBT-03",
        ("todo", 0),
        "doing",
        20,
        "بدأ: #447 مدموج (attendance.py صار حزمةً + سقّاطة حجم)، و#436 قلّص operations/models.py من 2,213 إلى 2,022.",
        [],
    ),
]


def sync(item_model):
    """تُطبِّق التحديثاتِ الحارسة؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, (old_status, old_progress), status, progress, line, title_swaps in UPDATES:
        item = item_model.objects.filter(code=code).first()
        if item is None or (item.status, item.progress) != (old_status, old_progress):
            continue
        item.status, item.progress = status, progress
        item.note = f"{item.note}\n{STAMP} {line}".strip()
        for old, new in title_swaps:
            item.title = item.title.replace(old, new)
        item.save(update_fields=["status", "progress", "note", "title", "updated_at"])
        changed.append(code)
    return changed


def forwards(apps, schema_editor):
    sync(apps.get_model("roadmap", "RoadmapItem"))


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
