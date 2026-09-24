"""مزامنةُ الخارطة يومَ 2026-09-24: Q-01/Q-02 وH-01 مُغلقة، وحسمُ D-16، ودَينُ حجم CSS، وعملٌ بلا بند.

حارسةٌ كـ0006: لا تلمس بنداً إلّا إن كانت حالتُه وتقدّمُه ما في آخر لقطة، ولا قراراً إلّا مفتوحاً؛
والملاحظةُ الموجودة لا تُلحَق ثانيةً؛ والبندُ الجديد يُنشأ إن غاب.

- **D-16** حسمه المالك في محادثة الخارطة يومَ 2026-09-23 («نعم صحيح، سجّله محسوماً») باعتماد توصيات
  جلسة الهويّة: سبعةُ أنماط، والفئةُ العريضة ≥1440، والكثافةُ مريحةٌ مبدئيّاً، واللوحةُ بشرائطَ وأعمدةٍ
  مكدّسة؛ وحدُّ اللوحيّ الأعلى لم يُحسم (مرتبطٌ بـD2 في خطّة الجوال).
- **LAY-01 لا يُغلق هنا:** مرجعُه `docs/design/page_layouts.md` في #517 الذي لم يندمج بعد — يُغلق في
  المزامنة التالية. وLAY-02 «قيد التنفيذ» الآن لأنّ العملَ جارٍ لا لأنّه دُمج.
"""

import datetime

from django.db import migrations

STAMP = "[2026-09-24]"
DAY = datetime.date(2026, 9, 24)

# (الرمز، (الحالة، التقدّم) المتوقَّعان، الحالة الجديدة، التقدّم الجديد، طلب الدمج، سطر الملاحظة)
UPDATES = [
    (
        "Q-01",
        ("doing", 60),
        "done",
        100,
        "#498 #507",
        "أُغلق: #507 وثيقةُ الرحلات (docs/mobile_user_journeys.md) — رحلةُ الوليّ الأسوأ: 61% دون 44px.",
    ),
    (
        "Q-02",
        ("doing", 60),
        "done",
        100,
        "#498 #507",
        "أُغلق: #507 فروقُ المحرّكين (docs/mobile_engine_differences.md) — الفرقُ في القياس 0.4 نقطة، "
        "و`vh`=`dvh` في المتصفّح الآليّ فلا يُكشف فرقُها إلّا على جهازٍ حقيقيّ.",
    ),
    (
        "H-01",
        ("todo", 0),
        "done",
        100,
        "#513",
        "أُغلق: #513 الحدودُ الدنيا الـ17 تقرأ var(--control-h) لا 44px حرفيّاً، وحارسٌ يمنع عودتها. "
        "و--tap-gap و--control-h-sm تُعرَّفان في M-01 حيث تُقرآن أوّلاً.",
    ),
    (
        "LAY-02",
        ("todo", 0),
        "doing",
        60,
        "",
        "المواصفاتُ مقبولة، وصفحةُ الدليل /styleguide/layouts/ مبنيّة، والمعيارُ مضافٌ إلى CLAUDE.md "
        "— في #517 المفتوح؛ بقي الدمج. (طلبُ جلسة الهويّة 8101.)",
    ),
]

# (الرمز، الحالة المتوقَّعة، الحالة الجديدة)
DECISIONS = [("D-16", "open", "decided")]

# بنودٌ جديدة: (الرمز، المصدر، المسار، العنوان، الحالة، التقدّم، طلب الدمج، الملاحظة)
NEW_ITEMS = [
    (
        "DBT-36",
        "DBT",
        "debt",
        "حجمُ CSS المشحون المصغَّر ≈262KB = 98.5% من سقف test_css_budget (266,240 بايت) وفوق هدف DoD "
        "(240KB): الهامشُ ≈4KB فكلُّ ميزةٍ تقترب من إسقاط البوّابة",
        "todo",
        0,
        "",
        "قيس 2026-09-23 على فرع H-03 بـtests/css_source.shipped_size(). #517 ينزله ≈2KB بنقل أصناف الدليل "
        "إلى ملفٍّ للمطوّر وحده؛ وH-03 يضيف ≈0.5KB. العلاجُ الجذريّ: قياسُ ما لا تستعمله صفحةٌ من القواعد.",
    ),
    (
        "N-022",
        "NEW",
        "frontend",
        "الإسناد: وقفٌ للمنسّقين وألوانُ الأقسام المركزيّة، وتصديرٌ بإشعارٍ عائم",
        "done",
        100,
        "#509",
        "عملٌ دُمج بلا بندٍ في الخارطة، سُجّل مُغلقاً برقم طلبه.",
    ),
    (
        "N-023",
        "NEW",
        "frontend",
        "تسجيلُ السلوك في قائمة «السلوك» لا في قوائم الجداول",
        "done",
        100,
        "#510",
        "عملٌ دُمج بلا بندٍ في الخارطة، سُجّل مُغلقاً برقم طلبه.",
    ),
    (
        "N-024",
        "NEW",
        "mobile",
        "الإدارة على الجوّال: قائمةٌ مطويّةٌ في سطرٍ واحد وأهدافُ لمسٍ 44px (ترويسةٌ 235 ← 152px)",
        "done",
        100,
        "#511",
        "عملٌ دُمج بلا بندٍ في الخارطة، سُجّل مُغلقاً برقم طلبه. يخصّ OWN-21 (الفحص البصريّ وأهدافُ اللمس).",
    ),
    (
        "N-025",
        "NEW",
        "ops",
        "خوادمُ الجلسات: طابورٌ وقنواتٌ باسم قاعدة الشجرة، وعاملٌ يقلع مع الخادم؛ وفحصُ صحّةٍ للعامل",
        "done",
        100,
        "#512 #516",
        "عملٌ دُمج بلا بندٍ في الخارطة، سُجّل مُغلقاً برقم طلبه.",
    ),
]

SORT_AFTER = {"DBT": 225, "NEW": 454}  # بعد DBT-35 (224) وبعد LAY-07 (453)


def sync(item_model):
    """تُطبِّق تحديثاتِ البنود الحارسة؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, expected, status, progress, pr, line in UPDATES:
        item = item_model.objects.filter(code=code).first()
        if item is None or (item.status, item.progress) != expected or line in item.note:
            continue
        item.status, item.progress = status, progress
        if pr:
            item.pr = pr
        item.note = f"{item.note}\n{STAMP} {line}".strip()
        item.save(update_fields=["status", "progress", "pr", "note", "updated_at"])
        changed.append(code)
    return changed


def decide(decision_model):
    """تحسم القراراتِ المفتوحة وحدها؛ تُرجع رموزَ ما حُسم."""
    decided = []
    for code, expected, status in DECISIONS:
        decision = decision_model.objects.filter(code=code, status=expected).first()
        if decision is None:
            continue
        decision.status, decision.decision_date = status, datetime.date(2026, 9, 23)
        decision.save(update_fields=["status", "decision_date", "updated_at"])
        decided.append(code)
    return decided


def add_missing(item_model):
    """تُنشئ البنودَ الغائبة؛ تُرجع رموزَ ما أُنشئ."""
    created, offsets = [], {}
    for code, src, lane, title, status, progress, pr, note in NEW_ITEMS:
        offset = offsets[src] = offsets.get(src, -1) + 1
        if item_model.objects.filter(code=code).exists():
            continue
        item_model.objects.create(
            code=code,
            src=src,
            lane=lane,
            title=title,
            status=status,
            progress=progress,
            start_date=DAY,
            end_date=DAY if status == "done" else None,
            date_basis="محدَّث يدوياً",
            pr=pr,
            note=f"{STAMP} {note}",
            sort_order=SORT_AFTER[src] + offset,
        )
        created.append(code)
    return created


def forwards(apps, schema_editor):
    item_model = apps.get_model("roadmap", "RoadmapItem")
    # قاعدةٌ بلا استيراد (اختبار، شجرةٌ جديدة): لا شيء يُزامَن، ولا بنودٌ يتيمة.
    if not item_model.objects.exists():
        return
    sync(item_model)
    decide(apps.get_model("roadmap", "RoadmapDecision"))
    add_missing(item_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0007_layout_system_items"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
