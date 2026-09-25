"""مزامنةُ الخارطة الحادية عشرة (2026-09-25): REP-04 (#588) وREP-01 (بعمليّة) وRK6 = 0، ودَينٌ جديدٌ DBT-56.

أرسلتها جلسةُ «دراسة شاملة لـ Git والفروع» (صاحبةُ عائلة REP)، وتحقّقتُ من #588 من نصّه المدموج (دُمج 2026-09-25 05:24Z، bb7038cd).

حارسةٌ كسابقاتها: لا تلمس بنداً إلّا إن كانت حالتُه وتقدّمُه ما في آخر لقطة؛ والملاحظةُ الموجودة لا تُلحَق ثانيةً؛ ورمزُ الطلب يُضاف
إلى الحقل لا يستبدله؛ ولا يُلمس مؤشّرٌ إلّا إن كانت قيمتُه وتاريخُ قياسه ما في آخر لقطة؛ ويُنشأ الدَّينُ الغائب مفتوحاً بلا تاريخ.

- **REP-04 → منجز** بـ#588، و**RK6 من 2 إلى 0**.
- **REP-01 → منجز بعمليّةٍ لا بطلب دمج** (بإذن المالك، كسابقة DBT-05) بما أفادت به جلسةُ Git، مع ذكر ما لم يصلني تفصيلُه.
- **REP-03** ملاحظةٌ فقط: التجهيزُ المحلّيّ منجز والمقارنةُ على الإنتاج بيد المالك؛ لا نسبةَ تقدّمٍ أُعطيت فلم يُغيَّر شيء.
- **DBT-56** دَينٌ مفتوحٌ جديدٌ نشأ من #588 (تحذيراتُ توثيق API مُسكَتة بمعرِّفَيها).

النصوصُ محايدةٌ عن قصد (المستودعُ عامّ): لا وصفَ لما تعرّض ولا أين ولا كم، ولا ثغرةً بمقياسها؛ والتفصيلُ في نصّ #588 نفسِه وفي المستودع الخاصّ.
"""

import datetime

from django.db import migrations

STAMP = "[2026-09-25]"
DAY = datetime.date(2026, 9, 25)
BASIS = "غير مجدول"

# (الرمز، (الحالة، التقدّم) المتوقَّعان، الحالة الجديدة، التقدّم الجديد، رمزُ الطلب يُضاف، سطر الملاحظة)
UPDATES = [
    (
        "REP-04",
        ("todo", 0),
        "done",
        100,
        "#588",
        "أُغلق: #588 (جلسة Git، دُمج 2026-09-25 05:24Z، bb7038cd، بإذن المالك): الخطواتُ الثلاثُ التي تلتقط مخرجَ أمرٍ بـ`| tee` صارت تُفعِّل "
        "pipefail، وبيئةُ وظيفة الفحص بمفاتيحَ وهميّةٍ، واختبارٌ يثبت أنّ الوظيفةَ تسقط حين ينهار أمرُها؛ وحرّاسٌ جديدةٌ (منها ما يمنع رجوعَ "
        "النمط في أيّ workflow) **تسقط على الصيغة القديمة: 4 فاشلة و2 ناجحة**. والفحصُ الحقيقيّ صار يعمل ويمرّ: «System check identified no "
        "issues (26 silenced)»؛ وفحوصُ الطلب 23 من 23 ثمّ فحوصُ الطابور. **RK6 من 2 إلى 0.** خريطةُ الحرّاس محدَّثةٌ في الطلب نفسه "
        "(docs/governance/regression_guards.md). ونشأ منه دَينٌ: تحذيراتُ توثيق API المُسكَتة بمعرِّفَين (DBT-56). **بعد آخر إخطار نشرٍ "
        "(main@6087da6)** فيُنشر في دورةٍ لاحقة؛ ولا أثرَ ظاهراً منه على الإنتاج.",
    ),
    (
        "REP-01",
        ("todo", 0),
        "done",
        100,
        "",
        "أُنجز **بعمليّةٍ لا بطلب دمج** (بإذن المالك، جلسةُ Git، 2026-09-25 نحو 06:10 بحسبها — سابقةُ DBT-05): حزمةُ git bundle محقَّقةٌ "
        "حجمُها 125.5MB على الجهاز ومهمّةٌ ليليّةٌ مجدولةٌ مسجَّلة. **لم يصلني تفصيلُ** الاستعادة التجريبيّة في مجلّدٍ معزولٍ وعددِ النسخ "
        "المحتفَظ بها (وهما من معيار البند)؛ واعتمدتُ إفادةَ الجلسة بإنجازه. **RK2 لا يتغيّر قبل REP-05:** النسخةُ على الجهاز نفسِه فليست "
        "نسخةً بعيدة.",
    ),
    (
        "REP-03",
        ("todo", 0),
        "todo",
        0,
        "",
        "بحسب جلسة Git (2026-09-25): التجهيزُ المحلّيّ منجزٌ والأداةُ مختبَرة؛ والمقارنةُ على الإنتاج ينفّذها المالكُ بنفسه — يبقى قيدَ التنفيذ. "
        "لم تُعطَ نسبةُ تقدّمٍ بحسابٍ صريح فلم يُغيَّر التقدّم (0).",
    ),
]

# (الرمز، (القيمة، تاريخ القياس) المتوقَّعان، القيمة الجديدة، مرجعُ القياس) — يُلحق المرجعُ بمصدر المؤشّر بحدّ الحقل 255
KPI_UPDATES = [
    (
        "RK6",
        (2.0, DAY),
        0.0,
        "بعد #588: 3 خطواتٍ تفعّل pipefail وحارسٌ يمنع رجوعَ النمط (سقطت الحرّاسُ على القديم)",
    ),
]

# دَينٌ مفتوحٌ جديد بلا تاريخٍ ولا طلب: (الرمز، المسار، العنوان، معيار الإغلاق، الملاحظة)
DEBTS = [
    (
        "DBT-56",
        "backend",
        "توثيقُ واجهة API: 26 تحذيراً مُسكَتاً في فحص النشر (drf-spectacular W001 وW002)",
        "قائمةُ SILENCED_SYSTEM_CHECKS تفرغ من معرِّفات drf_spectacular ويبقى فحصُ النشر نظيفاً (المعرِّفاتُ المُسكَتة 2 ← 0، والتحذيراتُ "
        "26 ← 0).",
        "نشأ من #588 (اقترحته جلسةُ Git): تحذيراتُ **توثيقٍ** لا أمانِ نشر — أنواعٌ ومُسلسِلاتٌ ناقصةٌ في api/ (W001×7 وW002×19) — أُسكِتت "
        "بمعرِّفَيها في shschool/settings/production.py بقائمةٍ يحرسها اختبارُ test_the_silenced_system_checks_are_only_the_known_"
        "documentation_warnings فلا تتّسع بصمت. البديلُ إصلاحُها في api/ (دَينٌ مستقلّ لا يُصفَّر في طلبٍ واحد). سُجّل مفتوحاً بلا تاريخ.",
    ),
]
DEBTS_FIRST_ORDER = 725  # بعد M-05b (724)


def _add_pr(existing, pr):
    """تُضيف رموزَ الطلبات الجديدة إلى ما في الحقل بلا تكرار."""
    return " ".join(dict.fromkeys([*existing.split(), *pr.split()]))


def sync(item_model):
    """تُطبِّق تحديثاتِ البنود الحارسة؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, expected, status, progress, pr, line in UPDATES:
        item = item_model.objects.filter(code=code).first()
        if item is None or (item.status, item.progress) != expected or line in item.note:
            continue
        item.status, item.progress = status, progress
        if pr:
            item.pr = _add_pr(item.pr, pr)
        item.note = f"{item.note}\n{STAMP} {line}".strip()
        item.save(update_fields=["status", "progress", "pr", "note", "updated_at"])
        changed.append(code)
    return changed


def _record(kpi, value):
    """تكتب قياسَ اليوم في السجلّ: تستبدل نقطةَ اليوم إن وُجدت، وإلّا تُلحقها."""
    today = DAY.isoformat()
    history = [point for point in (kpi.history or []) if point.get("d") != today]
    history.append({"d": today, "v": value})
    kpi.current, kpi.measured_at, kpi.history = value, DAY, history


def sync_kpis(kpi_model):
    """تُحدِّث المؤشّراتِ التي لم تُمسّ منذ آخر لقطة (والأساسُ باقٍ)؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, expected, value, source_note in KPI_UPDATES:
        kpi = kpi_model.objects.filter(code=code).first()
        if kpi is None or (kpi.current, kpi.measured_at) != expected:
            continue
        source = (
            kpi.source if source_note in kpi.source else f"{kpi.source} ({source_note})".strip()
        )
        if len(source) > 255:
            source = kpi.source
        _record(kpi, value)
        kpi.source = source
        kpi.save(update_fields=["current", "measured_at", "history", "source", "updated_at"])
        changed.append(code)
    return changed


def add_debts(item_model):
    """تُنشئ الديونَ الغائبةَ مفتوحةً بلا تاريخٍ ولا طلب؛ تُرجع رموزَ ما أُنشئ."""
    created = []
    for offset, (code, lane, title, criterion, note) in enumerate(DEBTS):
        if item_model.objects.filter(code=code).exists():
            continue
        item_model.objects.create(
            code=code,
            src="DBT",
            lane=lane,
            title=title,
            status="todo",
            progress=0,
            date_basis=BASIS,
            criterion=criterion,
            note=f"{STAMP} {note}",
            sort_order=DEBTS_FIRST_ORDER + offset,
        )
        created.append(code)
    return created


def forwards(apps, schema_editor):
    item_model = apps.get_model("roadmap", "RoadmapItem")
    # قاعدةٌ بلا استيراد (اختبار، شجرةٌ جديدة): لا شيء يُزامَن، ولا بنودٌ يتيمة.
    if not item_model.objects.exists():
        return
    sync(item_model)
    sync_kpis(apps.get_model("roadmap", "RoadmapKpi"))
    add_debts(item_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0022_sync_items_2026_09_25c"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
