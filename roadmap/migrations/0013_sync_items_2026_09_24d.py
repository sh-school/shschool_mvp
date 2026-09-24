"""مزامنةُ الخارطة الرابعة يومَ 2026-09-24: حسمُ D-17، وأثرُه على خطّة توليد الجدول، وما دُمج بعد 0011.

حارسةٌ كسابقاتها: لا تلمس بنداً إلّا إن كانت حالتُه وتقدّمُه ما في آخر لقطة؛ والملاحظةُ الموجودة لا تُلحَق
ثانيةً؛ والبندُ الجديد يُنشأ إن غاب؛ والقرارُ لا يُحسم إلّا إن كان مفتوحاً.

- **D-17** حسمه المالك يومَ 2026-09-24 **خلافَ التوصية**: «لا تكسر توزيع المادة لو سمحت ابدا قيد صلب»
  (نقلته جلسةُ الجدولة، وأكّده في محادثة الخارطة: «نعم صحيح، سجّله محسوماً»). فـHC6 قيدٌ صلبٌ لا رخصةَ له
  ولا يُحرَّر من الإدارة. وأثرُه: SCH-03 (السداد) احتياطٌ لا طريق، وSCH-05 يُفكّ حجبُه، وبندٌ جديد SCH-17.
- **OWN-19** يُغلق بـ#526 و#533، و**OWN-22** بـ#534، و**N-032** لـ#531 (اليومُ المبتور).
- **Q-12** يُغلق و**Q-08** إلى 60 بـ#537، و**MD9** (محسومٌ من قبل) تُلحق به ملاحظةُ تطبيق standalone.
- **لا يُلمس** ما لم يندمج: LAY-03 (#532 #539)، OWN-24 (#536).
"""

import datetime

from django.db import migrations

STAMP = "[2026-09-24]"
DAY = datetime.date(2026, 9, 24)

OWNER_RULING = "لا تكسر توزيع المادة لو سمحت ابدا قيد صلب"

# (الرمز، (الحالة، التقدّم) المتوقَّعان، الحالة الجديدة، التقدّم الجديد، طلب الدمج، سطر الملاحظة، البوّابة)
# البوّابة None = لا تُلمس. والحالةُ الجديدة كالمتوقَّعة = ملاحظةُ تقدّمٍ وحدها.
UPDATES = [
    (
        "OWN-19",
        ("doing", 90),
        "done",
        100,
        "#526 #533",
        "أُغلق: #533 أتمّ تعريبَ سجلّات axes — عمودُ الحالة وقيمُه، ومرشّحُ «حالة القفل»، وإجراءُ «حذف المحاولات "
        "المنتهية» ورسالتُه، وعناوينُ أقسام صفحة التفاصيل.",
        None,
    ),
    (
        "OWN-22",
        ("todo", 0),
        "done",
        100,
        "#534",
        "أُغلق: #534 الذيلُ من مصدرٍ واحد — base.html وadmin/_footer.html يضمّنان components/site_footer_line.html "
        "وcomponents/site_brand.html، وحارسٌ في tests/test_admin_theme.py يمنع نسخةً ثالثة.",
        None,
    ),
    (
        "SCH-03",
        ("doing", 5),
        "doing",
        5,
        "",
        "بعد حسم D-17: السدادُ احتياطٌ لا طريق — HC6 لا يُكسر، فما يتعذّر وضعُه يُعلَن باسمه (SCH-17) لا يُسدَّد.",
        None,
    ),
    (
        "SCH-05",
        ("doing", 0),
        "doing",
        0,
        "",
        "فُكّ حجبُه بحسم D-17: لا اعتمادَ لجدولٍ فيه مخالفةٌ لـHC6 أصلاً، والإقرارُ للمخالفات الصلبة الأخرى وحدها.",
        "",
    ),
    (
        "Q-12",
        ("todo", 0),
        "done",
        100,
        "#537",
        "أُغلق: #537 المانيفستان standalone بمعرّفٍ ثابت (/ و/parents/) ولا قفلَ اتّجاه؛ الحارس tests/test_pwa_install.py. "
        "(أبلغت به جلسةُ «اصلاحات 02».)",
        None,
    ),
    (
        "Q-08",
        ("todo", 0),
        "doing",
        60,
        "#537",
        "#537: touch-action: manipulation على التحكّمات وaria-current للشريط السفليّ؛ الحارس "
        "tests/test_touch_controls.py. الباقي: ترحيلُ font-size إلى rem (K24) مع H-03.",
        None,
    ),
    (
        "VI-24",
        ("todo", 0),
        "todo",
        0,
        "",
        "قياسُ جلسة الهويّة: أربعُ لوحاتٍ بطاقاتُها دون 240px حتى على 900px — شؤونُ الموظفين، والإشعارات، "
        "والأجنحة، ونظرةُ الحضور؛ تحتاج إعادةَ تخطيط.",
        None,
    ),
]

# بنودٌ جديدة: (الرمز، المصدر، المسار، العنوان، الحالة، التقدّم، طلب الدمج، ملاحظة، البداية، النهاية، الأساس، الترتيب)
NEW_ITEMS = [
    (
        "N-032",
        "NEW",
        "backend",
        "اليومُ المبتور: التوليدُ يُكمل اليومَ الناقص، وواجهةُ resync_sessions_for_range",
        "done",
        100,
        "#531",
        "عملٌ دُمج بلا بندٍ في الخارطة، سُجّل مُغلقاً برقم طلبه. كان يومٌ كُتب فيه إشغالٌ أو تبديلٌ أو تعويضٌ قبل "
        "توليد أسبوعه يبقى بحصّةٍ واحدة (1 بدل 176). يعتمد عليه SCH-08، ومصالحةُ الأسابيع المولَّدة سلفاً صارت "
        "فيه. والباقي مفتوحٌ لا يُغلق: وقتُ التعويض لا يراعي الطابقَ والخميس، ولا إشارةَ في Session إلى حصّتها "
        "في الخطّة، والجدولُ الأسبوعيّ الديناميكيّ (تصميمُه ينتظر المالك).",
        DAY,
        DAY,
        "محدَّث يدوياً",
        464,  # بعد N-031 (463)
    ),
    (
        "SCH-17",
        "SCH",
        "backend",
        "بحثٌ أقوى يضع كلَّ الحصص بلا كسرٍ لـHC6، وإلّا يُعلن «تعذّر وضع» باسم القيد",
        "todo",
        0,
        "",
        "من حسم D-17 (2026-09-24): HC6 قيدٌ صلبٌ لا رخصةَ له، فالسدادُ (SCH-03) احتياطٌ لا طريق. "
        "تواريخُه ورقمُ طلبه من جلسة الجدولة حين يُفتح.",
        None,
        None,
        "غير مجدول — ينتظر تاريخاً من جلسة الجدولة",
        617,  # بعد SCH-16 (616)
    ),
]

# (الرمز، الحالة المتوقَّعة، الحالة الجديدة، تاريخ الحسم، سطرٌ يُلحَق بالتوصية)
DECISIONS = [
    (
        "D-17",
        "open",
        "decided",
        DAY,
        f"حسمُ المالك خلافَ التوصية: «{OWNER_RULING}» — HC6 قيدٌ صلبٌ لا رخصةَ له ولا يُحرَّر من الإدارة.",
    ),
]


# قراراتٌ محسومةٌ من قبلُ تُلحَق بتوصيتها ملاحظةُ تطبيقٍ وحدها: (الرمز، سطر الملاحظة)
DECISION_NOTES = [
    (
        "MD9",
        "(ب) طُبّق بـ#537: standalone يحلّ محلّ fullscreen (قرار 2026-09-14، #264)؛ فوّض المالكُ الحسمَ "
        "(«تصرّف الأفضل للمنصّة وعرضها على جميع الأجهزة»)، والتفصيلُ في D9 بخطّة الجوال.",
    ),
]


def annotate_decisions(decision_model):
    """تُلحق ملاحظةَ التطبيق بالقرارات المحسومة وحدها، مرّةً واحدة؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, line in DECISION_NOTES:
        decision = decision_model.objects.filter(code=code, status="decided").first()
        if decision is None or line in decision.recommendation:
            continue
        decision.recommendation = f"{decision.recommendation}\n{STAMP} {line}".strip()
        decision.save(update_fields=["recommendation", "updated_at"])
        changed.append(code)
    return changed


def sync(item_model):
    """تُطبِّق تحديثاتِ البنود الحارسة؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, expected, status, progress, pr, line, gate in UPDATES:
        item = item_model.objects.filter(code=code).first()
        if item is None or (item.status, item.progress) != expected or line in item.note:
            continue
        item.status, item.progress = status, progress
        if pr:
            item.pr = pr
        if gate is not None:
            item.gate = gate
        item.note = f"{item.note}\n{STAMP} {line}".strip()
        item.save(update_fields=["status", "progress", "pr", "gate", "note", "updated_at"])
        changed.append(code)
    return changed


def add_missing(item_model):
    """تُنشئ البنودَ الغائبة؛ تُرجع رموزَ ما أُنشئ."""
    created = []
    for code, src, lane, title, status, progress, pr, note, start, end, basis, order in NEW_ITEMS:
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
            pr=pr,
            note=f"{STAMP} {note}",
            sort_order=order,
        )
        created.append(code)
    return created


def decide(decision_model):
    """تحسم القراراتِ المفتوحة وحدها، وتُلحق نصَّ الحسم بالتوصية؛ تُرجع رموزَ ما حُسم."""
    decided = []
    for code, expected, status, when, line in DECISIONS:
        decision = decision_model.objects.filter(code=code, status=expected).first()
        if decision is None:
            continue
        decision.status, decision.decision_date = status, when
        if line not in decision.recommendation:
            decision.recommendation = f"{decision.recommendation}\n{STAMP} {line}".strip()
        decision.save(update_fields=["status", "decision_date", "recommendation", "updated_at"])
        decided.append(code)
    return decided


def forwards(apps, schema_editor):
    item_model = apps.get_model("roadmap", "RoadmapItem")
    # قاعدةٌ بلا استيراد (اختبار، شجرةٌ جديدة): لا شيء يُزامَن، ولا بنودٌ يتيمة.
    if not item_model.objects.exists():
        return
    decision_model = apps.get_model("roadmap", "RoadmapDecision")
    decide(decision_model)
    annotate_decisions(decision_model)
    sync(item_model)
    add_missing(item_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0012_schedule_generation_plan"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
