"""الخارطةُ الحاديةُ والأربعون (2026-10-03): نشرُ 4723849 — إغلاقُ N-081 (سجلُّ الكادر)، وتقدّمُ N-074 (#812 رصدُ الغياب بالمعلّم الفعليّ)،
وامتدادُ حماية المحو (#813 #816)، وجودةُ الجدول (#817)، ومقاييسُ mypy وCSS (الهامشُ قربَ حدّ الأحمر).

حارسةٌ كسابقاتها: لا يُلمس بندٌ إلّا إن طابقت حالتُه وتقدّمُه (أو مؤشّرٌ: قيمتُه وتاريخُ قياسه) آخرَ لقطة، ولا تُكرَّر ملاحظةٌ.

**N-081 يُغلق** بنشر #809 (تأكيدُ الدفتر وجلسة النشر)؛ والقياسُ منسوبٌ لجلسة التنفيذ لا لي.
**N-074 يتقدّم ولا يُغلق:** ما بقي «محجوبٌ بقرار المالك» (إخطارُ وليّ الأمر بالتأخّر، محاسبةُ المشرف، عضويّةُ طالبٍ↔مجموعةٍ متوازية).
**V-K01:** الهامشُ 535 بايتاً قربَ حدّ الأحمر 512؛ لا أنسبُ سببَ النزول لطلبٍ بعينه.

والمستودعُ عامّ: نصوصٌ محايدة بلا تفاصيل ثغراتٍ ولا بياناتٍ شخصيّة.
"""

import datetime

from django.db import migrations

STAMP = "[2026-10-03]"
D = datetime.date
DAY = D(2026, 10, 3)

# (الرمز، (الحالة، التقدّم) المتوقَّعان، الحالة الجديدة، التقدّم الجديد، رمزُ طلبٍ يُضاف، سطر الملاحظة)
UPDATES = [
    (
        "N-081",
        ("doing", 90),
        "done",
        100,
        "",
        "**نُشر فعلاً:** #809 (W-20261002-044) منشورٌ منذ 10:22 بتوقيت الدوحة (الدفتر `published`، وe5fe48c يعلنه /health/). **قياسُ جلسة التنفيذ 0404 (1366×768 على خادم جلستها بالشيفرة نفسها، CI أخضر بعدها — لا قياسي ولا قياسُ 0702):** "
        "الأسماءُ الملتفّة 0 من 50 (كانت 39)، الأعمدةُ 12 ← 9 (10 للمغادرين)، ارتفاعُ الصفّ 50–62px (كان 55–100)، «الدخول» عند المغادرين 119px (كان 13px) بلا تمريرٍ أفقيّ، وعلى الجوال 375 بطاقةٌ لكلّ منتسب بلا تمريرٍ أفقيّ. "
        "**ما بقي:** خيارُ المالك الاختياريّ بدمج العنوان وشريط المرشّحات في شريطٍ واحد (+صفّ) — لم يُقرَّر.",
    ),
    (
        "N-074",
        ("doing", 30),
        "doing",
        70,
        "#812",
        "**#812 نُشر main@1bb4c80f (2026-10-03، W-20261002-020؛ الدفتر `published` منذ 11:07 بتوقيت الدوحة):** رصدُ الغياب بالمعلّم الفعليّ واعتمادُه — سجلُّ حضورٍ attendance_ledger يُضاف إليه ولا يُمحى، "
        "هجراتُ operations 0062–0064 (توسيعٌ فقط)، selectors وشاشاتُ اعتمادٍ وتصحيح، وحرّاسٌ جديدة (test_student_attendance_writers وtest_attendance_ledger_readers_guard وtest_attendance_teacher_changes_s7). "
        "**قياسُ جلسة التنفيذ 0406 لا قياسي:** المجموعةُ الكاملة 10937 ناجحاً والإخفاقاتُ بيئيّةٌ على مضيفها (PDF/Chromium/axes). "
        "**ما بقي ولا يُحتسب منجزاً (محجوبٌ بقرار المالك):** إخطارُ وليّ الأمر بالتأخّر (D-139م)، ومحاسبةُ المشرف (conduct_rules §4 بند 5/8)، وعضويّةُ طالبٍ↔مجموعةٍ متوازية (T-P1). **التقدّم 70% اشتقاقٌ لا قياس.**",
    ),
]

# ملاحظاتٌ على بنودٍ قائمة تُلحق مرّةً واحدة بلا لمس الحالة ولا التقدّم: (الرمز، السطر)
NOTES = [
    (
        "N-075",
        "**امتدادٌ بطلبَين نُشرا ضمن main@4723849 (2026-10-03):** #813 (W-20261003-013) محوُ الطالب يُفرِّغ IP والمتصفّحَ من سجلّ التدقيق بزنادٍ يسمح بذلك وحدَه (قرارُ المالك بصفته مسؤولَ حماية البيانات، هجرةُ core 0078، "
        "وشرطُ 0105 بعلَم المعاملة)؛ و#816 (W-20261003-026) لا يُعاد نصُّ استثناءٍ للعميل في واجهات الرصد والمحو — جدولُ رسائلَ بالرمز، مع اختبارِ تسرّبٍ وحارسٍ ساكن (تنبيهاتُ CodeQL). "
        "**ملاحظةُ 0702 (قياسٌ لها): سقّاطةُ الطبقات get_school صارت 177 (كانت 176، +1 في api/views_erasure.py بسجلٍّ مرفوعٍ بلا accepted)؛ لا أنسب السببَ قبل تحقّقها.** ما زال بلا قياسِ تشغيلِ محوٍ حقيقيٍّ على الإنتاج.",
    ),
    (
        "N-071",
        "**#815 نُشر ضمن main@4723849 (2026-10-03، W-031):** مسارُ الحَكَم في test_security_gate من موضع الملفّ لا من مجلّد التشغيل — يُغلق ملاحظةَ 0105 P3 («مسارٌ نسبيّ») المذكورةَ في هذا البند. تبقى الأخرى: merge_group لم يُقَس، وCODEOWNERS (W-032)، وإعفاءُ Security Scan على push.",
    ),
    (
        "SCH-25",
        "**#817 نُشر main@47238494 (2026-10-03، W-20261003-010):** عمودُ الجودة يقدّم الصحّةَ على الدرجة (مسوّدةٌ فيها 3 متعذّراتٍ و5 مخالفاتٍ كانت تُعلن «100%» فوق جدولين كاملين «99%»)، فالمسوّدةُ الناقصةُ أو المكسورةُ تُوسَم «ناقصة» وتُفرَز تحت كلّ سليم؛ "
        "وسببُ المتعذّر صار يُعدّ في خانات الشعبة الفارغة لا المشغولة (امتلاءُ الشعبة رقمٌ). **الطلبُ نفسُه يقول «ليس أثرَ #798».** اختباراتٌ جديدة: test_schedule_quality_display وtest_scheduler_audit. "
        "**قياسُ جلسة التنفيذ 0403 (لا قياسي):** مسوّدةٌ 868/871 بثلاثة متعذّراتٍ كانت تُعرض فوق جدولين كاملين، و90 اختباراً ناجحاً؛ "
        "**ما بقي:** الجذرُ نفسُه (25 شعبةً بلا فراغ، والمولّدُ لا يحلّ التعبئةَ التامّة) معلَّقٌ بقرار المالك بين فراغٍ أكاديميّ أو محرّك CP-SAT (V2، SCH-22) — لا أسجّل حكماً.",
    ),
    (
        "QCC-10",
        "**#818 دُمج main@bacfa0d4 ولم يُنشر بعدُ (2026-10-03):** تعطيلُ الجمع الكسول داخل اختبار صفحة الحالة — فشلٌ متقطّعٌ كان يُسقط pytest تحت xdist (ذكره الطلبُ #812/#801). يعالج الفشلَ المتقطّعَ الذي كتبتُه «غيرَ مُعاد إنتاجه» في هذا البند.",
    ),
]

# (الرمز، (القيمة الحاليّة، تاريخ القياس) المتوقَّعان، القيمة الجديدة، تاريخُ القياس الفعليّ، مرجعُ القياس يُلحق بمصدر المؤشّر)
KPI_UPDATES = [
    (
        "V-K01",
        (273230.0, D(2026, 10, 3)),
        274921.0,
        D(2026, 10, 3),
        "0702، shipped_size() في حاوية بلا شبكة على main@1bb4c80f، 2026-10-03: 274,921 من سقف 275,456، الهامش 535 بايتاً قربَ حدّ الأحمر 512",
    ),
    (
        "PK6",
        (1219.0, D(2026, 10, 3)),
        1217.0,
        D(2026, 10, 3),
        "0702، «فحص الأنواع» في بوّابة الجودة (طابور الدمج) على main@1bb4c80f، 2026-10-03: 1,217 خطأً في 121 ملفّاً",
    ),
]


def _add_pr(existing, token):
    """تُضيف رمزَ الطلب دون تكرارٍ ودون تجاوز حدّ الحقل 64 (وإلّا يبقى الحقلُ كما هو)."""
    if not token:
        return existing
    joined = " ".join(dict.fromkeys([*existing.split(), *token.split()]))
    return joined if len(joined) <= 64 else existing


def _record(kpi, value, measured_date):
    """تكتب قياسَ تاريخِه الفعليّ في السجلّ: تستبدل نقطةَ ذلك اليوم إن وُجدت، وإلّا تُلحقها."""
    day = measured_date.isoformat()
    history = [point for point in (kpi.history or []) if point.get("d") != day]
    history.append({"d": day, "v": value})
    kpi.current, kpi.measured_at, kpi.history = value, measured_date, history


def _with_source(kpi, note):
    """تُلحق مرجعَ القياس بالمصدر دون تكرارٍ وبحدّ الحقل 255؛ عند التجاوز تُسقط أقدمَ مرجعٍ بين قوسين من
    المصدر القديم (لا القياسَ الجديد) حتى يتّسع، فلا يبقى قياسٌ بلا مرجعٍ صامتاً."""
    if not note:
        return kpi.source
    if note in kpi.source:
        return kpi.source
    candidate = f"{kpi.source} ({note})".strip()
    if len(candidate) <= 255:
        return candidate
    base = kpi.source
    while True:
        start = base.find("(")
        end = base.find(")", start)
        if start == -1 or end == -1:
            break
        base = (base[:start] + base[end + 1 :]).strip()
        candidate = f"{base} ({note})".strip() if base else f"({note})"
        if len(candidate) <= 255:
            return candidate
    return f"({note})"[:255]


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


def sync_notes(item_model):
    """تُلحق الملاحظاتِ بالبنود القائمة مرّةً واحدة بلا لمس الحالة؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, line in NOTES:
        item = item_model.objects.filter(code=code).first()
        if item is None or line in item.note:
            continue
        item.note = f"{item.note}\n{STAMP} {line}".strip()
        item.save(update_fields=["note", "updated_at"])
        changed.append(code)
    return changed


def sync_kpi_values(kpi_model):
    """تُحدِّث المؤشّراتِ التي لم تُمسّ منذ آخر لقطة؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, expected, value, measured_date, note in KPI_UPDATES:
        kpi = kpi_model.objects.filter(code=code).first()
        if kpi is None or (kpi.current, kpi.measured_at) != expected:
            continue
        source = _with_source(kpi, note)
        _record(kpi, value, measured_date)
        kpi.source = source
        kpi.save(update_fields=["current", "measured_at", "history", "source", "updated_at"])
        changed.append(code)
    return changed


def forwards(apps, schema_editor):
    item_model = apps.get_model("roadmap", "RoadmapItem")
    # قاعدةٌ بلا استيراد (اختبار، شجرةٌ جديدة): لا شيء يُزامَن، ولا بنودٌ يتيمة.
    if not item_model.objects.exists():
        return
    kpi_model = apps.get_model("roadmap", "RoadmapKpi")
    sync(item_model)
    sync_notes(item_model)
    sync_kpi_values(kpi_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0053_sync_items_2026_10_03d"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
