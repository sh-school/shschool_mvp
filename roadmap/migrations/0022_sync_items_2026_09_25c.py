"""مزامنةُ الخارطة العاشرة (2026-09-25): #583 «الشعار: الأصلُ المسطَّح مرجعاً وحيداً» — تنفيذٌ جزئيٌّ لـVI-11 وقرارِ VD4.

حارسةٌ كسابقاتها: لا تلمس بنداً إلّا إن كانت حالتُه وتقدّمُه ما في آخر لقطة؛ والملاحظةُ الموجودة لا تُلحَق ثانيةً؛ ورمزُ الطلب يُضاف إلى
الحقل لا يستبدله؛ ولا يُملأ مؤشّرٌ إلّا إن لم يُقَس قطّ؛ ولا تُحسم قراراتٌ ولا تُغيَّر مواعيد.

- **VI-11 → قيد التنفيذ 50%** بحسابٍ صريحٍ من جلسة الهويّة 8104 (قاسته على main@6087da69 مقابل main@16b179a0): عنوانُه تسليمان، «شعار SVG»
  منجزٌ و«أبعاد الصور الأربع» لم يبدأ (0 من 4)؛ ومعيارُ «الصفحة أخفّ ≥ 40KB» لا يُحتسب تقدّماً لأنّه لم يتحقّق مقيساً (الخامّ 34,167 بايتاً).
  وأرقامُ الملفّات تحقّقتُ منها بنفسي من main بالبايت.
- **V-K39 = 0** (فلاترُ التبييض؛ كانت 4) ونسخُ الشعار نصّاً في مصدره.
- ملاحظةٌ على القرار VD4 بأنّه نُفّذ جزئيّاً بـ#583 (يبقى محسوماً). والطلبُ منشورٌ على الإنتاج (main@6087da6).

لا يُغلق VI-11، ولا يُغيَّر موعدُه (11-02 ← 11-04 مقترَح).
"""

import datetime

from django.db import migrations

STAMP = "[2026-09-25]"
DAY = datetime.date(2026, 9, 25)

# (الرمز، (الحالة، التقدّم) المتوقَّعان، الحالة الجديدة، التقدّم الجديد، رمزُ الطلب يُضاف، سطر الملاحظة)
UPDATES = [
    (
        "VI-11",
        ("todo", 0),
        "doing",
        50,
        "#583",
        "#583 (8104، main@6087da69، 2026-09-25 05:09Z؛ **منشورٌ على الإنتاج** main@6087da6 نحو 08:20 الدوحة بلا هجرات — الأصولُ المبصومة (emblem-white وapple-touch-icon وfavicon) وأيقوناتُ المانيفست الأربع تُخدَم 200، و/health/ سليم، والدخول 200، وصفرُ أخطاء في الخدمات الثلاث): الشقُّ الأوّلُ من عنوان البند «شعار SVG» **منجز**، "
        "وتنفيذٌ لقرار VD4 بنطاقه المعدَّل: الأصلُ المسطَّح static/brand/logoMaroon.png مرجعاً وحيداً؛ static/brand/emblem.svg وemblem-white.svg "
        "متّجهان مُتتبَّعان منه (18,260 بايتاً خاماً لكلٍّ منهما)، ويعيد scripts/build_emblem.py اشتقاقَهما بايتاً ببايت؛ الترويسةُ ودخولُ المنصّة "
        "وترويسةُ الإدارة وصفحاتُ الخطأ تقرأ emblem-white.svg وحُذفت فلاترُ التبييض الأربعة؛ والأيقوناتُ بلونٍ واحدٍ #8A1538 (icon-512 من "
        "205KB إلى 16KB، وfavicon من 60KB إلى 7KB). حارسٌ tests/test_brand_emblem.py (تطابقُ الشكل مع الأصل: القديمةُ 0.40 والجديدةُ ≥ 0.86)؛ "
        "ومصدرُ CSS 467,156 ← 467,088 بايتاً (−68). **النسبةُ 50% اشتقاقُ 8104 بحسابٍ صريح:** عنوانُ البند تسليمان — «شعار SVG» منجز، "
        "و«أبعاد الصور الأربع» لم يبدأ (K19_img_without_dimensions = 4 قبلُ و4 بعدُ، أي 0 من 4). **ولم يُحتسب معيارُ «الصفحة أخفّ ≥ 40KB» "
        "تقدّماً لأنّه لم يتحقّق مقيساً:** وزنُ شعار صفحة الدخول 59,854 ← 25,687 بايتاً (18,260 لـemblem-white.svg + 7,427 لـfavicon.png) "
        "فالتوفيرُ الخامّ 34,167 بايتاً دون 40KB، وبضغط brotli للـSVG (6,088) يصير نحو 46,339 — **تقديرٌ لم يُقَس على الإنتاج**. **ولا يتحقّق "
        "حرفيّاً «بلا تغيّر بصريّ»:** تغيّر رسمُ الشعار عمداً (المسطَّحُ الأصليّ بدل المنقوش) بقرار المالك. **لم يُعاين:** صفحاتُ الخطأ "
        "مرسومةً، والأيقوناتُ على جهازٍ مثبَّت (تتحدّث الأيقوناتُ المثبَّتةُ حين يحدّث المتصفّحُ المانيفست؛ والمعاينةُ البصريّةُ عند المالك). **الباقي:** أبعادُ الصور الأربع (K19)، وقياسُ الوزن على الإنتاج، وSVG رسميّ من مدير المدرسة إن "
        "وُجد. والهدفُ «SVG + معكوس» (V-K39) يتحقّق بنسختَين مشتقّتَين لا رسميّتَين — يُقرأ كذلك. لم يُغيَّر موعدُه (11-02 ← 11-04 مقترَح).",
    ),
]

# (الرمز، القيمة الأولى، الوحدة، مرجعُ القياس) — يُملأ مؤشّرٌ نصّيّ الأساس لم يُقَس قطّ
FIRST_READINGS = [
    (
        "V-K39",
        0.0,
        "count",
        "بعد #583: فلاترُ التبييض 0 (كانت 4) بمسح tests/test_brand_emblem.py؛ ونسختان متّجهيّتان مشتقّتان من logoMaroon.png "
        "(build_emblem.py) ولا ملفّ رسميّ من جهةٍ بعدُ (0)",
    ),
]

# (الرمز، الحالة المتوقَّعة، سطر الملاحظة) — ملاحظةٌ على قرارٍ محسوم بلا لمس حالته
DECISION_NOTES = [
    (
        "VD4",
        "decided",
        "نُفِّذ جزءٌ منه بـ#583 (الأصلُ المسطَّح مرجعاً وحيداً ونسخةٌ بيضاءُ بلا فلتر تبييض)؛ VI-11 قيد التنفيذ 50% ولم يُغلق.",
    ),
]


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


def first_readings(kpi_model):
    """تملأ القيمةَ الحاليّةَ لمؤشّرٍ نصّيّ الأساس إن لم يُقَس قطّ (بحدّ حقل المصدر 255)؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, value, unit, source_note in FIRST_READINGS:
        kpi = kpi_model.objects.filter(
            code=code, current__isnull=True, measured_at__isnull=True
        ).first()
        if kpi is None:
            continue
        source = (
            kpi.source if source_note in kpi.source else f"{kpi.source} ({source_note})".strip()
        )
        if len(source) > 255:
            source = kpi.source
        _record(kpi, value)
        if unit and not kpi.unit:
            kpi.unit = unit
        kpi.source = source
        kpi.save(
            update_fields=["current", "measured_at", "history", "unit", "source", "updated_at"]
        )
        changed.append(code)
    return changed


def annotate_decisions(decision_model):
    """تُلحق ملاحظةً بقرارٍ محسومٍ مرّةً واحدة بلا تغيير حالته؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, expected, line in DECISION_NOTES:
        decision = decision_model.objects.filter(code=code, status=expected).first()
        if decision is None or line in decision.recommendation:
            continue
        decision.recommendation = f"{decision.recommendation}\n{STAMP} {line}".strip()
        decision.save(update_fields=["recommendation", "updated_at"])
        changed.append(code)
    return changed


def forwards(apps, schema_editor):
    item_model = apps.get_model("roadmap", "RoadmapItem")
    # قاعدةٌ بلا استيراد (اختبار، شجرةٌ جديدة): لا شيء يُزامَن، ولا بنودٌ يتيمة.
    if not item_model.objects.exists():
        return
    sync(item_model)
    first_readings(apps.get_model("roadmap", "RoadmapKpi"))
    annotate_decisions(apps.get_model("roadmap", "RoadmapDecision"))


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0021_sync_items_2026_09_25b"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
