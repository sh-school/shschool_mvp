"""الخارطةُ التاسعةُ والثلاثون (2026-10-03): نشرُ 2eb3641 — «حالةُ اليوم» (QCC-10، المرحلةُ 1) وإغلاقُ N-079 (تقصيرُ CLAUDE.md).

حارسةٌ كسابقاتها: لا يُلمس بندٌ إلّا إن طابقت حالتُه وتقدّمُه آخرَ لقطة، ولا تُكرَّر ملاحظةٌ، ولا يُنشأ بندٌ موجود.

**N-079 يُغلق** لأنّ #806 (main@73d848c8) سلفٌ للإيداع المنشور 2eb36411 (تحقّقٌ بغيت، وتأكيدٌ من جلسة النشر أنّ الإنتاج على 2eb3641).
**QCC-10:** المرحلةُ 1 فقط منشورة؛ المراحلُ التالية (إشعارُ المالك 07:15) محجوبةٌ بقرار المالك — فلا done.

والمستودعُ عامّ: نصوصٌ محايدة.
"""

import datetime

from django.db import migrations

STAMP = "[2026-10-03]"
D = datetime.date
DAY = D(2026, 10, 3)

# (الرمز، (الحالة، التقدّم) المتوقَّعان، الحالة الجديدة، التقدّم الجديد، رمزُ طلبٍ يُضاف، سطر الملاحظة)
UPDATES = [
    (
        "N-079",
        ("doing", 90),
        "done",
        100,
        "",
        "**نُشر فعلاً:** #806 (main@73d848c8) سلفٌ للإيداع 2eb36411 المنشور على الإنتاج (تحقّقٌ بغيت، وتأكيدُ جلسة النشر أنّ الإنتاج على 2eb3641) — CLAUDE.md بـ142 سطراً والقواعدُ بالمسار حيّان.",
    ),
]

# بنودٌ جديدة: (الرمز، المصدر، المسار، العنوان، الاعتماديّات، المعيار، الحالة، التقدّم، البداية، النهاية، أساسُ التاريخ، الجهد، البوّابة، طلب الدمج، المرجع، الملاحظة، الترتيب)
NEW_ITEMS = [
    (
        "QCC-10",
        "QCC",
        "ops",
        "مركزُ قيادة الجودة: صفحةُ «حالةُ اليوم» ولوحةُ الطابور — المرحلة 1",
        "QCC-09",
        "صفحةٌ /command-center/status/ تجيب أسئلةَ المالك الأربعة، ولوحةُ «الطابورُ والنشر» (collectors/queue.py)، ورابطُ «حالةُ اليوم» بهدف لمسٍ 44px على الجوّال؛ حارسُ المسارات واختباراتٌ؛ **ثمّ** المراحلُ التالية (إشعارُ المالك 07:15).",
        "doing",
        50,
        D(2026, 10, 2),
        None,
        "W-20261002-022 (المرحلة 1)، نُشر main@2eb3641 (2026-10-03)",
        3.0,
        "owner",
        "#801",
        "W-034",
        "**بندٌ جديدٌ بقاعدة الإدراج (عائلةُ QCC، آخرُ رمزٍ كان QCC-09).** نُشر بتأكيدٍ مباشرٍ من جلسة النشر، وأُعيد نشرُ celery-worker وcelery-beat على c5fa7427 (SUCCESS للاثنتين). "
        "**المقيس (جلسة التنفيذ):** axe نجح على 8f54d62c؛ ولقطةُ nurse--clinic_dashboard الحمراءُ انجرافُ تاريخٍ (02/10 مقابل 03/10 في الأساس) لا من العمل. "
        "**لم يُقَس:** ظهورُ الصفحة وعملُها على الإنتاج بعد النشر، واستمرارُ نجاح pytest (فشلٌ متقطّعٌ واحدٌ في test_the_page_answers_the_owners_four_questions لم يُعَد إنتاجُه؛ إصلاحٌ محلّيٌّ عند 0801 غيرُ مدفوع). "
        "**المراحلُ التالية (إشعارُ المالك 07:15، W-034) محجوبةٌ بقرار المالك فالبوّابةُ owner**؛ والتقدّمُ 50% اشتقاقٌ (مرحلةٌ من عدّةِ مراحل) لا قياس.",
        807,
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
    add_new_items(item_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0051_sync_items_2026_10_03b"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
