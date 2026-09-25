"""مزامنةُ الخارطة التاسعةَ عشرة (2026-09-25 مساءً): ما نُشر على main@a213d3c (نحو 18:58 الدوحة، بشهادة جلسة النشر).

حارسةٌ كسابقاتها: لا يُلمس بندٌ إلّا إن كانت حالتُه وتقدّمُه ما في آخر لقطة، ولا تُكرَّر ملاحظةٌ، ورمزُ الطلب يُضاف بحدّ الحقل 64، ويُنشأ الغائبُ وحدَه.
والمستودعُ عامّ: نصوصٌ محايدة. **لا يُغلق بندٌ بلا قياس:** ما لم يُتحقَّق حيّاً يُذكر في ملاحظته وتقدّمُه اشتقاقٌ لا قياس.

- **U-20 → منجز** (#612): مرشّحُ تاريخٍ واحدٍ بجانب أزرار الأسبوع الأربعة. **U-40 → قيد التنفيذ** (#613): الكودُ منشورٌ والأثرُ الحيّ ينتظر إضافةَ الأحداث بقرار المالك.
- **N-044 جديد** (#611): مهمّةٌ يوميّةٌ تُنهي طلباتِ التعويض المفتوحة التي مضى يومُها — أوّلُ تشغيلٍ حيّ فجرَ 09-26.
- **ملاحظاتٌ:** D-23 (#610) نُفِّذ وأُلحق بـLAY-08 وقرارِه؛ #618 على REP-18 وU-19 (سطرُ CLAUDE.md أُصلح؛ ولا تقدّمَ يُسجَّل قبل تحقّق خضرة Nightly وQuality الأسبوعيّ).
"""

import datetime

from django.db import migrations

STAMP = "[2026-09-25]"
D = datetime.date


# (الرمز، (الحالة، التقدّم) المتوقَّعان، الحالة الجديدة، التقدّم الجديد، رفعُ البوّابة، رمزُ الطلب يُضاف، سطر الملاحظة)
UPDATES = [
    (
        "U-20",
        ("todo", 0),
        "done",
        100,
        True,
        "#612",
        "**U-20 منجز ومنشور (#612، ضمن main@a213d3c نحو 18:58 الدوحة):** حقلُ تاريخٍ واحدٌ بجانب أزرار الأسبوع الأربعة (السابق/التالي/هذا الأسبوع/الخطّة) "
        "بـdata-autosubmit المركزيّ وform-control-sm وبلا CSS جديد. المقيس (8061، الطلب نفسُه): 75 اختباراً بحرّاس الهويّة والوصوليّة تمرّ. تفسيرُ معيار "
        "«الفلتر الموحّد يعمل بأزراره الأربعة» أكّده المالكُ في جلسة 8061 (نقلٌ لا تأكيدٌ مباشرٌ لجلسة الخارطة). **لم يُتحقَّق:** معاينةُ حقل التاريخ بصريّاً "
        "على الإنتاج (عند المالك). وموعدُه الأصليّ (10-26..11-30) لم يُعدَّل.",
    ),
    (
        "U-40",
        ("todo", 0),
        "doing",
        33,
        False,
        "#613",
        "**U-40: الكودُ منشورٌ (#613، ضمن main@a213d3c) والأثرُ الحيّ ينتظر:** حدثُ students_end وحالةُ ENDED في school_days (مقيَّدةٌ بنطاق الصفّ، بلا أثرٍ "
        "على عامٍ بلا الحدث ولا تسرّبٍ للعام التالي)؛ 12 اختباراً، وحدّا البدء والنهاية باستعلامٍ واحد فبقيت اختباراتُ الأداء سليمة، وسجلُّ الطبقات ثبّت نقصاً "
        "حقيقيّاً في wings/views.py (13←12). **لا أثرَ حيّاً حتى تُضاف الأحداث:** التواريخُ المبذورة **مشتقّةٌ** من آخر يومٍ في اختبارات الفصل الثاني "
        "(2026-27) لا من نشرة الوزارة، وموسومةٌ في اسم الحدث، والبذرُ يمسح أحداثَ العام فلا يُشغَّل على الإنتاج — فإضافةُ الأحداث بقرار المالك وتأكيد تواريخها. "
        "**التقدّم 33% = خطوةٌ من ثلاث (الكودُ منشور؛ إضافةُ الأحداث؛ تأكيدُ التواريخ) — اشتقاقٌ لا قياس، ولا يُوسم منجَزاً** (اقتراحُ 8061).",
    ),
]

# بنودٌ جديدة: (الرمز، المصدر، المسار، العنوان، الاعتماديّات، المعيار، الحالة، التقدّم، البداية، النهاية، أساسُ التاريخ، الجهد، البوّابة، طلب الدمج، المرجع، الملاحظة، الترتيب)
NEW_ITEMS = [
    (
        "N-044",
        "NEW",
        "backend",
        "الحصّة التعويضيّة: طلباتُها المفتوحة التي مضى يومُها تنتهي تلقائيّاً (مهمّةٌ يوميّة expire_overdue)",
        "",
        "مهمّةٌ يوميّةٌ مجدولةٌ (4:15 الدوحة) تُنهي طلباتِ التعويض المفتوحةَ التي مضى يومُها مع بقاء القاعدة القديمة (>14 يوماً)؛ واختبارٌ؛ وأوّلُ تشغيلٍ "
        "حيٍّ يظهر في سجلّ العامل («expire_overdue: expired N requests» إن وُجد ما يُنهى).",
        "doing",
        67,
        D(2026, 9, 25),
        D(2026, 9, 26),
        "أوّلُ تشغيلٍ حيّ فجرَ 09-26 الساعة 4:15 الدوحة",
        1.0,
        "",
        "#611",
        "جلسة الجدول 8061",
        "الكودُ منشورٌ (#611، ضمن main@a213d3c نحو 18:58 الدوحة): المهمّةُ مسجَّلةٌ في Celery وبندُ beat expire-overdue-compensatory موجود؛ 13 اختباراً "
        "(8061، الطلب نفسُه). **لم يُقَس تشغيلُها الحيّ:** أوّلُ تشغيلٍ فجرَ 09-26 — يُقرأ سجلُّ العامل بعده (عند جلسة النشر/مسار التشغيل) فيُسجَّل القياسُ ويُغلق "
        "البند. **بلا إشعارٍ للمعلّم عند الانتهاء** (قرارٌ للمالك لم يُتَّخذ). **التقدّم 67% = خطوتان من ثلاث (الكودُ والنشر ✓؛ أوّلُ تشغيلٍ حيّ ✗) — اشتقاقٌ لا قياس.** "
        "لم يكن للعمل بندٌ فعُيِّن N-044 (قاعدةُ الإدراج: ملاحظةٌ ← ابنٌ ← عائلةٌ ← N-…؛ وN-033 وN-039 مغلقان بمعيارَين آخرَين).",
        735,
    ),
]

# ملاحظاتٌ على بنودٍ قائمة تُلحق مرّةً واحدة (بلا لمس الحالة ولا التقدّم)
NOTES = [
    (
        "LAY-08",
        "**#610 نفّذ D-23 (منشور ضمن main@a213d3c نحو 18:58 الدوحة؛ 8061):** شريطُ أدوات الجدول لا يفيض في اللوحيّ — الالتفافُ من 641 إلى 1028px وnowrap "
        "من 1029 (اختار المالكُ 1029 لا 1025). المقيس بعد الإصلاح على الصفحة نفسها بإطاراتٍ بعرضٍ دقيق: 17 عرضاً (641…1280) فيضُ المستند = 0 في كلّها، وعند "
        "1025–1028 مع فرض nowrap = 0؛ وقبله 79px عند 900 و16 عند 1024؛ وحارسٌ ساكنٌ (test_mobile_layout) سقط على القديم؛ والملفُّ أصغرُ من main بـ263 بايتاً. "
        "**لم يُعاين بصريّاً على الإنتاج** (عند المالك). لم تُغيَّر حالةُ البند ولا تقدّمُه (يبقى الباقي من العيوب).",
    ),
    (
        "REP-18",
        "**#618 دُمج ونُشر (ضمن main@a213d3c نحو 18:58 الدوحة) — لا تقدّمَ يُسجَّل قبل التحقّق:** فيه الشقُّ التنفيذيّ: تثبيتُ متصفّحات Playwright وعزلُها في "
        "quality.yml الأسبوعيّ، ومهلةٌ لـmutmut (كان يدور ستَّ ساعاتٍ فيُلغى)، وحارسان جديدان، وإصلاحُ علّة اختبار التنقّل (زرعُ الحصّة في تاريخ الاستمارة "
        "نفسِه)؛ 112 اختباراً محلّيّاً (8097). **معيارُ البند (لا وظيفةٌ مجدولةٌ حمراءٌ دائمة) يُتحقَّق بخضرة Nightly (ليلةَ 09-25) وQuality الأسبوعيّ (الأحد 09-27)** — "
        "ولم يتمّ بعد؛ يُسجَّل بما يقيسه 8204/8097.",
    ),
    (
        "U-19",
        "**#618 أصلح سطرَ CLAUDE.md** (الإشارةُ إلى railway-migrate.sh غيرِ الموجود ← railway-predeploy.sh، بإذن المالك؛ تحقّقتُ أنّه على main). **يبقى:** "
        "حذفُ Grafana وتثبيتُ sentry-sdk وسكربتا backup/restore القديمان وحسمُ docs/protocols — فلا يُغلق البند ولا يتغيّر تقدّمُه.",
    ),
]

# ملاحظاتٌ على قراراتٍ محسومة: (الرمز، سطر الملاحظة) — لا تُغيَّر الحالةُ
DECISION_NOTES = [
    (
        "D-23",
        "نُفِّذ بـ#610 (نُشر ضمن main@a213d3c نحو 18:58 الدوحة): الالتفافُ من 641 إلى 1028px وnowrap من 1029؛ القياسُ والتحفّظُ في ملاحظة LAY-08.",
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
            pr=pr,
            ref=ref,
            note=f"{STAMP} {note}",
            sort_order=order,
        )
        created.append(code)
    return created


def sync_notes(item_model):
    """تُلحق الملاحظاتِ بالبنود القائمة مرّةً واحدة؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, line in NOTES:
        item = item_model.objects.filter(code=code).first()
        if item is None or line in item.note:
            continue
        item.note = f"{item.note}\n{STAMP} {line}".strip()
        item.save(update_fields=["note", "updated_at"])
        changed.append(code)
    return changed


def sync_decision_notes(decision_model):
    """تُلحق ملاحظةً بقرارٍ محسومٍ مرّةً واحدة دون تغيير حالته؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, line in DECISION_NOTES:
        decision = decision_model.objects.filter(code=code, status="decided").first()
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
    add_new_items(item_model)
    sync_notes(item_model)
    sync_decision_notes(apps.get_model("roadmap", "RoadmapDecision"))


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0031_kpi_readings_2026_09_25"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
