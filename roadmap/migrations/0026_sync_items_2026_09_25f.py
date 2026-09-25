"""مزامنةُ الخارطة الرابعةَ عشرة (2026-09-25): قراراتُ المالك RD1 وRD3 وما يترتّب عليهما، وREP-02، و#596، وتصحيحُ توقيتَين مقدَّرَين.

حارسةٌ كسابقاتها: لا يُلمس بندٌ إلّا إن كانت حالتُه وتقدّمُه (ومواعيدُه حين تُغيَّر) ما في آخر لقطة، ولا تُكرَّر ملاحظةٌ، ورمزُ الطلب
يُضاف لا يستبدل (وبحدّ الحقل 64)، ولا يُحسم إلّا قرارٌ ما زال مفتوحاً. والمستودعُ عامّ: لا رقمٌ شخصيّ ولا تجزئةٌ طويلة ولا وصفٌ لمادّةٍ حسّاسة.

- **قراران للمالك (2026-09-25) أكّدهما لجلسة Git ثمّ لجلسة الخارطة مباشرةً:** RD3 — نافذةُ U-03 (إعادةُ كتابة التاريخ) الجمعة
  2026-10-02، تبدأ الخميسَ 10-01 بعد 14:00 وتنتهي السبتَ 10-03؛ وRD1 — يبقى المستودعُ عامّاً حتى نافذة إعادة الكتابة (احتواءٌ
  بالنافذة لا بالتحويل إلى خاصّ). RD4 (قرارُ الإخطار) يبقى مفتوحاً عند المسؤول.
- **ما يترتّب على RD3:** U-03 يُنقل من 2026-09-25 إلى 10-01..10-03 وتُضاف اعتماديّاتُه (REP-01 وREP-03 وREP-06 وREP-07 وREP-08 وRD1 وRD3
  وRD7) ويُضاف «التحقّقُ يفتح الأرشيفات (RK4 = 0)» إلى معيار إغلاقه؛ وU-02 تنتهي 2026-09-29 ويُغلق بإغلاق REP-05؛ وفي ميتا الخارطة:
  المَعلَمُ والمسارُ الحرجُ ونصُّ النوافذ فقط. **لا يُمَسّ وصفُ هدف المرحلة P0** (المراحلُ بنيةُ المالك) **ولا موعدُ U-01** (لم يُحسم).
- **REP-02 → قيد التنفيذ 25%** باقتراح جلسة Git (خطوةٌ من أربعٍ متساوية) لا قياس؛ والصياغةُ محايدةٌ كما طلبت.
- **REP-05 → منجز** بإفادة جلسة Git (وُسمت الأعمالُ الفريدة ودُفعت الوسومُ بإذن المالك) و**RK2 من 5 إلى 0** (`git ls-remote --tags` مقابل أطراف الفروع).
- **SCH-08:** ملاحظةُ #596 (اندمج 2026-09-25 10:11 بالدوحة، لم يُنشر بعدُ)؛ وتبقى 95% حتى النشر والقياس النهائيّ صباحَ الأحد.
- **تصحيحُ توقيتَين مقدَّرَين** في #598 (صحّحتهما 8033): «نحو 10:50» في SCH-08 و«نحو 11:15» في N-041.
- **LAY-03:** قياسٌ تكميليٌّ لـ#587 (8101) وتنبيهُ هامش CLS في ميزانيّة الأداء.
"""

import copy
import datetime

from django.db import migrations

STAMP = "[2026-09-25]"
DAY = datetime.date(2026, 9, 25)
META_KEY = "roadmap"


D = datetime.date


# تصحيحُ نصٍّ قائمٍ في ملاحظة بندٍ (الرمز، القديم، الجديد) — يُطبَّق ما دام القديمُ موجوداً فيها (لا يتكرّر)
CORRECTIONS = [
    (
        "N-041",
        "الجمعة 2026-09-25 نحو 11:15 الدوحة",
        "الجمعة 2026-09-25 نحو 10:00 الدوحة",
    ),
    (
        "SCH-08",
        "(2026-09-25 نحو 10:50 الدوحة، قياسٌ قرائيٌّ على الإنتاج)",
        "(صباحَ 2026-09-25، قياسٌ قرائيٌّ على الإنتاج)",
    ),
]

# (الرمز، (الحالة، التقدّم) المتوقَّعان، الحالة الجديدة، التقدّم الجديد، رفعُ البوّابة، رمزُ الطلب يُضاف، سطر الملاحظة)
UPDATES = [
    (
        "SCH-08",
        ("doing", 95),
        "doing",
        95,
        False,
        "#596",
        "**#596 اندمج (main@c7e97cc3، 2026-09-25 10:11 بالدوحة، 8033):** المادّةُ جزءٌ من هويّة الجلسة في مصالحة الجلسات، فتُستبدل جلسةٌ "
        "تبدّلت مادّتُها تحت المعلّم نفسه (الثغرةُ التي كشفها التحقّقُ المبكّر على الإنتاج: 3 جلساتٍ بمادّةٍ قديمة)، باختبارَين. **لم يُنشر "
        "بعدُ** — ينتظر دفعةَ جلسة النشر. **تبقى النسبةُ 95%** (اقتراحُ 8033) حتى يُنشر ويُقاس نهائيّاً صباحَ الأحد 2026-09-27 (06:47 "
        "بالدوحة، مجدوَلٌ آلياً في جلستها) فتُبلغ لرفعها إلى 100%.",
    ),
    (
        "REP-02",
        ("todo", 0),
        "doing",
        25,
        False,
        "",
        "**REP-02:** سُجّلت المراجعةُ في وحدة /breach/ (2026-09-25)؛ التقييمُ والقرارُ عند المسؤول (RD4 مفتوح). **التقدّم 25% = خطوةٌ من "
        "أربعٍ متساوية** (أولاها التسجيلُ بوقت الاكتشاف الفعليّ، وتفصيلُ البقيّة في مستودع الوثائق الخاصّ) — اقتراحُ جلسة Git لا قياس، "
        "وقرارُ الحالة والنسبة للمالك.",
    ),
    (
        "REP-05",
        ("todo", 0),
        "done",
        100,
        True,
        "",
        "**REP-05 منجز:** وُسمت الأعمالُ الفريدة ودُفعت الوسومُ (بإذن المالك الصريح، بعد فحص المحتوى قبل الدفع لأنّ المستودعَ عامّ)؛ "
        "RK2 = 0 (2026-09-25). والفروعُ قابلةٌ للحذف بلا فقدان عند REP-08. ومصيرُ أيّ عملٍ فريدٍ اكتُشف بعد القياس الأوّل (إكمالٌ أو "
        "أرشفة) قرارُ المالك ولا يمسّ هذا الإغلاق. القياسُ: أطرافُ الفروع مقابل الوسوم في origin، 2026-09-25 (نقلتها جلسةُ Git بلغةٍ محايدة).",
    ),
]

# (الرمز، (القيمة، تاريخ القياس) المتوقَّعان، القيمة الجديدة، مرجعُ القياس) — يُلحق المرجعُ بمصدر المؤشّر بحدّ الحقل 255
KPI_UPDATES = [
    ("RK2", (5.0, DAY), 0.0, "بعد REP-05 (2026-09-25): الوسومُ مدفوعةٌ وتطابق أطرافَ الفروع"),
]

# (الرمز، (الحالة، التقدّم) المتوقَّعان، سطر الملاحظة) — ملاحظةٌ فقط بلا لمس الحالة ولا التقدّم
NOTES = [
    (
        "LAY-03",
        ("doing", 50),
        "قياسٌ تكميليٌّ لـ#587 من 8101: وسيطُ FCP −12ms ووسيطُ LCP −16ms. **تنبيهٌ لميزانيّة الأداء:** صندوقُ الإشعارات عند 1280×720 "
        "يقيس CLS 0.074 — هامشٌ ضيّقٌ من سقف 0.1 في test_web_vitals_budget، وهو أوّلُ مشتبَهٍ إن اقترب الحارسُ من سقفه. لم تُغيَّر "
        "الحالةُ ولا التقدّمُ ولا الموعد.",
    ),
]

# قراراتُ المالك المؤكَّدة: (الرمز، الحالة المتوقَّعة، الحالة الجديدة، سطر الحسم) — لا يُحسم إلّا ما ما زال مفتوحاً
DECISIONS = [
    (
        "RD1",
        "open",
        "decided",
        "قرارُ المالك (2026-09-25، أكّده لجلسة Git ثمّ لجلسة الخارطة مباشرةً): يبقى المستودعُ عامّاً حتى نافذة إعادة الكتابة "
        "(احتواءٌ بالنافذة لا بالتحويل إلى خاصّ).",
    ),
    (
        "RD3",
        "open",
        "decided",
        "قرارُ المالك (2026-09-25، أكّده لجلسة Git ثمّ لجلسة الخارطة مباشرةً): نافذةُ U-03 الجمعة 2026-10-02 (تبدأ الخميسَ 10-01 بعد "
        "14:00 وتنتهي السبتَ 10-03).",
    ),
]

RESCHEDULE_BASIS = "قرارُ المالك RD3 (2026-09-25) — كان {old}"

# نقلُ موعدِ بندٍ تبعاً لـRD3: (الرمز، (الحالة، التقدّم، البداية، النهاية) المتوقَّعة، البداية الجديدة، النهاية الجديدة،
# اعتماديّاتٌ تُضاف، جملةٌ تُلحق بمعيار الإغلاق، الموعدُ القديم للأساس، سطر الملاحظة)
RESCHEDULES = [
    (
        "U-02",
        ("doing", 50, D(2026, 9, 21), D(2026, 9, 24)),
        D(2026, 9, 21),
        D(2026, 9, 29),
        ["REP-05"],
        "",
        "2026-09-24",
        "بعد RD3 (قرارُ المالك 2026-09-25): تنتهي 2026-09-29 بدل 09-24، ويُغلق بإغلاق REP-05 (خمسةُ وسومٍ موصوفةٍ والفروعُ الخمسةُ "
        "قابلةٌ للحذف بلا فقدان) وقد أُضيف REP-05 إلى اعتماديّاته. لم تُغيَّر حالتُه ولا تقدّمُه.",
    ),
    (
        "U-03",
        ("todo", 0, D(2026, 9, 21), D(2026, 9, 25)),
        D(2026, 10, 1),
        D(2026, 10, 3),
        ["REP-01", "REP-03", "REP-06", "REP-07", "REP-08", "RD1", "RD3", "RD7"],
        "التحقّقُ يفتح الأرشيفات (RK4 = 0)",
        "2026-09-25",
        "بعد RD3 (قرارُ المالك 2026-09-25): النافذةُ الجمعةَ 2026-10-02 (تبدأ الخميسَ 10-01 بعد 14:00 وتنتهي السبتَ 10-03) بدل "
        "2026-09-25؛ أُضيفت اعتماديّاتُ REP-01 وREP-03 وREP-06 وREP-07 وREP-08 وRD1 وRD3 وRD7، وأُضيف «التحقّقُ يفتح الأرشيفات "
        "(RK4 = 0)» إلى معيار الإغلاق. لم تُغيَّر حالتُه ولا تقدّمُه.",
    ),
]

# تعديلاتُ ميتا الخارطة (نصٌّ داخل عنصرٍ في قائمة): (المفتاح، القديم، الجديد)
META_TEXT_EDITS = [
    (
        "windows",
        "نافذة الجمعة 2026-09-25 (عطلة المدرسة): U-01 ثم U-03",
        "نافذة الجمعة 2026-10-02 (عطلة المدرسة؛ تبدأ الخميس 10-01 بعد 14:00 — قرارُ المالك RD3 2026-09-25): U-03 بعد U-01",
    ),
    (
        "rules",
        "نافذة الجمعة 2026-09-25 محجوزة لـU-01/U-03؛ لا عمل موازٍ فيها.",
        "نافذة U-03 الجمعة 2026-10-02 (تبدأ الخميس 10-01 بعد 14:00) محجوزة؛ لا عمل موازٍ فيها (قرارُ المالك RD3 2026-09-25).",
    ),
    ("criticalPath", "(قبل 09-24)", "(قبل 09-29)"),
]
# المَعلَم: يُنقل من 2026-09-25 إلى 2026-10-02 ويُعاد وصفُه
MILESTONE_OLD_DATE = "2026-09-25"
MILESTONE_NEW_DATE = "2026-10-02"
MILESTONE_OLD_PART = "U-01 ثم U-03"
MILESTONE_NEW_PART = "U-03 بعد U-01"
MILESTONE_SUFFIX = " — قرارُ المالك RD3 2026-09-25"
# المسارُ الحرج: عنصرُ U-03 يُلحق به موعدُ النافذة
CRITICAL_PATH_PREFIX = "U-03 تدوير"
CRITICAL_PATH_SUFFIX = " نافذتُه الجمعة 2026-10-02 (قرارُ المالك RD3 2026-09-25)."
CRITICAL_PATH_MARK = "2026-10-02"


def correct(item_model):
    """تصحّح نصَّ التوقيتين المقدَّرَين في الملاحظات القائمة؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, old, new in CORRECTIONS:
        item = item_model.objects.filter(code=code).first()
        if item is None or old not in item.note:
            continue
        item.note = item.note.replace(old, new)
        item.save(update_fields=["note", "updated_at"])
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


def _add_pr(existing, token):
    """تُضيف رمزَ الطلب دون تكرارٍ ودون تجاوز حدّ الحقل 64 (وإلّا يبقى الحقلُ كما هو)."""
    if not token:
        return existing
    joined = " ".join(dict.fromkeys([*existing.split(), *token.split()]))
    return joined if len(joined) <= 64 else existing


def sync(item_model):
    """تُطبِّق تحديثاتِ البنود الحارسة؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, expected, status, progress, clear_gate, pr, line in UPDATES:
        item = item_model.objects.filter(code=code).first()
        if item is None or (item.status, item.progress) != expected or line in item.note:
            continue
        item.status, item.progress = status, progress
        item.pr = _add_pr(item.pr, pr)
        if clear_gate:
            item.gate = ""
        item.note = f"{item.note}\n{STAMP} {line}".strip()
        item.save(update_fields=["status", "progress", "pr", "gate", "note", "updated_at"])
        changed.append(code)
    return changed


def decide(decision_model):
    """تحسم القراراتِ المفتوحة وحدها وتُلحق نصَّ الحسم بالتوصية؛ تُرجع رموزَ ما حُسم."""
    decided = []
    for code, expected, status, line in DECISIONS:
        decision = decision_model.objects.filter(code=code, status=expected).first()
        if decision is None:
            continue
        decision.status, decision.decision_date = status, DAY
        if line not in decision.recommendation:
            decision.recommendation = f"{decision.recommendation}\n{STAMP} {line}".strip()
        decision.save(update_fields=["status", "decision_date", "recommendation", "updated_at"])
        decided.append(code)
    return decided


def _merge_deps(existing, additions):
    """تُضيف الاعتماديّاتِ الغائبةَ بفاصلةٍ عربيّة دون تكرار وبحدّ الحقل 255 (وإلّا يبقى كما هو)."""
    present = existing.strip()
    missing = [dep for dep in additions if dep not in present]
    if not missing:
        return existing
    joined = "، ".join(missing) if present in ("", "—") else f"{present}، " + "، ".join(missing)
    return joined if len(joined) <= 255 else existing


def reschedule(item_model):
    """تنقل مواعيدَ U-02/U-03 تبعاً لـRD3 ما لم يحرّكها المطوّر؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, expected, start, end, deps, criterion_part, old_end, line in RESCHEDULES:
        item = item_model.objects.filter(code=code).first()
        if item is None or line in item.note:
            continue
        if (item.status, item.progress, item.start_date, item.end_date) != expected:
            continue
        item.start_date, item.end_date = start, end
        item.date_basis = RESCHEDULE_BASIS.format(old=old_end)
        item.deps = _merge_deps(item.deps, deps)
        if criterion_part and criterion_part not in item.criterion:
            item.criterion = f"{item.criterion}؛ {criterion_part}".strip("؛ ")
        item.note = f"{item.note}\n{STAMP} {line}".strip()
        item.save(
            update_fields=[
                "start_date",
                "end_date",
                "date_basis",
                "deps",
                "criterion",
                "note",
                "updated_at",
            ]
        )
        changed.append(code)
    return changed


def sync_notes(item_model):
    """تُلحق الملاحظاتِ بالبنود القائمة (لا حالةَ ولا تاريخ) مرّةً واحدة؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, expected, line in NOTES:
        item = item_model.objects.filter(code=code).first()
        if item is None or (item.status, item.progress) != expected or line in item.note:
            continue
        item.note = f"{item.note}\n{STAMP} {line}".strip()
        item.save(update_fields=["note", "updated_at"])
        changed.append(code)
    return changed


def edit_meta(meta_model):
    """تنقل نافذةَ U-03 في ميتا الخارطة (النوافذ والقواعد والمَعلَم والمسار الحرج) ولا تمسّ المراحلَ؛ تُرجع مفاتيحَ ما تغيّر."""
    meta = meta_model.objects.filter(key=META_KEY).first()
    if meta is None or not isinstance(meta.data, dict):
        return []
    data = copy.deepcopy(meta.data)
    changed = []
    for key, old, new in META_TEXT_EDITS:
        seq = data.get(key)
        if not isinstance(seq, list):
            continue
        for index, text in enumerate(seq):
            if isinstance(text, str) and old in text and new not in text:
                seq[index] = text.replace(old, new)
                if key not in changed:
                    changed.append(key)
    milestones = data.get("milestones")
    if isinstance(milestones, list):
        for milestone in milestones:
            if (
                isinstance(milestone, dict)
                and milestone.get("d") == MILESTONE_OLD_DATE
                and MILESTONE_OLD_PART in str(milestone.get("name", ""))
            ):
                milestone["d"] = MILESTONE_NEW_DATE
                milestone["name"] = (
                    milestone["name"].replace(MILESTONE_OLD_PART, MILESTONE_NEW_PART)
                    + MILESTONE_SUFFIX
                )
                if "milestones" not in changed:
                    changed.append("milestones")
    path = data.get("criticalPath")
    if isinstance(path, list):
        for index, text in enumerate(path):
            if (
                isinstance(text, str)
                and text.startswith(CRITICAL_PATH_PREFIX)
                and CRITICAL_PATH_MARK not in text
            ):
                path[index] = text + CRITICAL_PATH_SUFFIX
                if "criticalPath" not in changed:
                    changed.append("criticalPath")
    if changed:
        meta.data = data
        meta.save(update_fields=["data", "updated_at"])
    return changed


def forwards(apps, schema_editor):
    item_model = apps.get_model("roadmap", "RoadmapItem")
    # قاعدةٌ بلا استيراد (اختبار، شجرةٌ جديدة): لا شيء يُزامَن، ولا بنودٌ يتيمة.
    if not item_model.objects.exists():
        return
    correct(item_model)
    decide(apps.get_model("roadmap", "RoadmapDecision"))
    reschedule(item_model)
    sync(item_model)
    sync_kpis(apps.get_model("roadmap", "RoadmapKpi"))
    sync_notes(item_model)
    edit_meta(apps.get_model("roadmap", "RoadmapMeta"))


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0025_sync_kpis_2026_09_25"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
