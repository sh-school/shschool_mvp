"""الخارطةُ الثانيةُ والثلاثون (2026-10-02): دفعةُ 29/9–1/10 الكبيرة — G2 منشورةٌ، نواةُ CP-SAT لمولّد V2 (ADR-0008)،
عارضُ md المركزيّ، إصلاحُ عدّاد الطلاب، استيرادُ سجلّ القيد الوزاريّ، ولوحتا «ما نُشر اليوم» وحالة النسخ الاحتياطيّ.

حارسةٌ كسابقاتها: لا يُلمس بندٌ إلّا إن طابقت حالتُه وتقدّمُه (أو مؤشّرٌ: قيمتُه وتاريخُ قياسه) آخرَ لقطة، ولا تُكرَّر ملاحظةٌ، ولا بندَ يُغلق بلا قياسٍ.

**بنودٌ لا نشرَ مؤكَّداً لها بعد:** N-056 (#752) — أمينُ البلاغات صرّح بعدم تحقّقه من النشر؛ يبقى doing حتى يصل تأكيدٌ مباشر.

والمستودعُ عامّ: نصوصٌ محايدة.
"""

import datetime

from django.db import migrations

STAMP = "[2026-10-02]"
D = datetime.date
DAY = D(2026, 10, 2)

# (الرمز، (الحالة، التقدّم) المتوقَّعان، الحالة الجديدة، التقدّم الجديد، رمزُ طلبٍ يُضاف، سطر الملاحظة)
UPDATES = [
    (
        "SCH-20",
        ("done", 100),
        "done",
        100,
        "#747",
        "**#747 نُشر main@877ff568 (2026-09-29):** طوابعُ زمنيّةٌ (created_at/updated_at) على ScheduleSlot وTeacherPreference — تدقيقٌ إضافيٌّ لا يغيّر سلوكَ البند المُغلَق.",
    ),
    (
        "SCH-21",
        ("doing", 30),
        "doing",
        40,
        "#741 #748",
        "**#741 (G2) نُشر main@450e48ea ثمّ main@ae15f5e5 (2026-09-29/30، تأكيدٌ مباشرٌ من 0601):** رتبةُ كسر HC5 صارت NEVER افتراضاً (كانت RELAXED) — 4 من 10 مخالفات HC5 كانت تمرّ صامتةً قبل الإصلاح. **G2 منجزٌ.** "
        "**#748 نُشر main@404f6bf6 (2026-10-01):** فصلُ ثابت التلاصق (HC5) عن ثابت المزدوجة الشرعيّة — تصليبٌ إضافيّ. **التقدّم 40% = أربعٌ من عشرة (G1 وG2 وG4-أ وD-61م ✓)، الباقي G3 وG4-ب وG5 وG6 (المعلَّقُ على قرار مالكٍ مفتوح).**",
    ),
    (
        "N-050",
        ("doing", 90),
        "doing",
        90,
        "#743",
        "**#743 نُشر main@72162eec (2026-09-30، قرارُ المالك D-70م):** تذييلُ PDF المركزيّ الافتراضيّ صار «SchoolOS» بلا رقم إصدار (كان «SchoolOS v6») — يحسم W-028 المرتبط بهذا البند. **المتبقّي كما كان: معاينةُ المالك على استمارةٍ حقيقيّة.**",
    ),
]

# بنودٌ جديدة: (الرمز، المصدر، المسار، العنوان، الاعتماديّات، المعيار، الحالة، التقدّم، البداية، النهاية، أساسُ التاريخ، الجهد، البوّابة، طلب الدمج، المرجع، الملاحظة، الترتيب)
NEW_ITEMS = [
    (
        "QCC-07",
        "QCC",
        "ops",
        "مركزُ قيادة الجودة: لوحةُ «ما نُشر اليوم»",
        "",
        "لوحةٌ في مركز قيادة الجودة تعرض كلَّ ما دُمج ونُشر خلال اليوم الجاريّ بمصدره (رقمُ الطلب والطابعُ الزمنيّ).",
        "done",
        100,
        D(2026, 9, 29),
        DAY,
        "W-20260929-017، نُشر main@d10a5313 (2026-09-29)",
        1.0,
        "",
        "#738 #753",
        "",
        "**بندٌ جديدٌ بقاعدة الإدراج (عائلةُ QCC، آخرُ رمزٍ كان QCC-06):** #738 أنشأ اللوحة. #753 (W-20260930-001) أصلح KeyError في جامعَي «ما نُشر اليوم»/pulls عند خلوّ قاموس النشر من stamp/sha — إصلاحٌ تابعٌ لا بندَ مستقلّاً له. 57 اختباراً + ruff/mypy نظيفان.",
        772,
    ),
    (
        "QCC-08",
        "QCC",
        "ops",
        "مركزُ قيادة الجودة: حالةُ النسخ الاحتياطيّ",
        "",
        "لوحةٌ تعرض حالةَ النسخ الاحتياطيّ: لا رجوعَ إلى الوراء في القيم المعروضة، وتحذيرٌ صريحٌ عند ردٍّ قديم، والرمزُ المرجعيّ إن ضُبط.",
        "done",
        100,
        D(2026, 9, 29),
        DAY,
        "W-20260929-014، نُشر main@81641546 (2026-09-29)",
        1.0,
        "",
        "#742",
        "",
        "**بندٌ جديدٌ بقاعدة الإدراج (عائلةُ QCC).**",
        773,
    ),
    (
        "N-052",
        "N",
        "ops",
        "سكربتُ شحنٍ بأمرٍ واحد (ship.sh) وبوّابةُ شروط الدمج الآليّ (auto_merge_gate.py)",
        "",
        "scripts/ship.sh يُنفِّذ تسلسلَ الشحن المعتاد بأمرٍ واحد؛ scripts/auto_merge_gate.py يفحص شروطَ الدمج الآليّ قبل تفعيله. سكربتا CI/CD فقط، لا كودَ منصّةٍ ولا هجرة.",
        "done",
        100,
        D(2026, 9, 29),
        DAY,
        "W-015/016، نُشر main@46d0a574 (2026-09-29)، الدمجُ والنشرُ بأمر المالك المباشر عبر 0501",
        1.0,
        "",
        "#739",
        "",
        "**بندٌ جديدٌ بقاعدة الإدراج (لا بندَ قائمٌ يغطّيه؛ أتمتةُ النشر).** أبلغت 0406 باندماجه.",
        774,
    ),
    (
        "SCH-22",
        "SCH",
        "backend",
        "مولّدُ الجدول V2: نواةٌ أساسيّةٌ بـCP-SAT (ADR-0008)",
        "SCH-09 · SCH-21",
        "ADR-0008 موثَّقٌ ومعتمَد؛ مواصفةُ قيود V2 كاملةٌ بنموذجٍ مرجعيّ؛ حزمةُ اختبارٍ مقنَّعةٌ (masked) تغطّي القيودَ الصلبة قبل استبدال المولّد الحاليّ فعليّاً.",
        "doing",
        15,
        D(2026, 10, 1),
        None,
        "تقريرُ مسحٍ عالميّ (timetabling_world_benchmark) + قرارُ v2_schedule_discussion: V2 امتدادُ SCH- لا وثيقةٌ جديدة",
        6.0,
        "",
        "#757 #759 #760 #766",
        "ADR-0008",
        "**بندٌ جديدٌ بقاعدة الإدراج (عائلةُ SCH-، بدايةُ V2):** #757 (ADR-0008: CP-SAT نواةً أساسيّةً) و#759 (توثيقٌ مرجعيّ) و#760 (مواصفةُ القيود + حزمةُ اختبارٍ مقنَّعة + تحديثُ المولّد) و#766 (وسمُ النطاق + AS-1..AS-6 + فحصُ جدوى الإسناد). "
        "**لا استبدالَ للمولّد الحاليّ بعدُ** — توثيقٌ ومواصفاتٌ وحزمةُ اختبارٍ فقط. التقدّمُ 15% اشتقاقٌ تقريبيّ (توثيقٌ+مواصفةٌ من عدّةِ مراحلَ متوقَّعة، لا قياسَ دقيقاً).",
        775,
    ),
    (
        "N-053",
        "N",
        "frontend",
        "عارضُ ملفّات md المركزيّ (docs_viewer)",
        "",
        "عارضٌ مركزيٌّ لملفّات Markdown داخل المنصّة بدل فتحها خاماً؛ .dockerignore يسمح بوصول الحاوية إلى ملفّات md اللازمة للعرض.",
        "done",
        100,
        D(2026, 9, 30),
        DAY,
        "W-20260930-002، نُشر main@f1ae5212 (2026-09-30)؛ D-82م، نُشر main@17585d9f (2026-10-01)",
        2.0,
        "",
        "#746 #763",
        "",
        "**بندٌ جديدٌ بقاعدة الإدراج (لا بندَ قائمٌ يغطّيه).** #746 أنشأ العارض، #763 فتح .dockerignore لملفّات md أمامه (امتدادٌ مباشر).",
        776,
    ),
    (
        "N-054",
        "N",
        "backend",
        "إصلاحُ عدّاد الطلاب المضلِّل + إعادةُ تنظيم صفحة استيراد/تصدير الطلاب",
        "",
        "count_students_enrolled_in_year يستند إلى StudentEnrollment (عامٌ دراسيّ) لا Membership.is_active (غيرُ مرتبطٍ بعام)؛ صفحةُ الاستيراد/التصدير ببطاقتين متجاورتين ومنطقةِ رفعٍ دائمةِ الظهور.",
        "done",
        100,
        D(2026, 10, 1),
        DAY,
        "W-20261001-034، نُشر main@bd68a728 (2026-10-01)",
        2.0,
        "",
        "#756",
        "",
        "**بندٌ جديدٌ بقاعدة الإدراج.** **قياسٌ حقيقيٌّ على بيانات مدرسة الشحانية:** العدّادُ الخاطئ 892 صار 735، مطابقٌ لتأكيد المالك المباشر. 7/7 اختباراتِ وحدةٍ ناجحة.",
        777,
    ),
    (
        "N-055",
        "N",
        "backend",
        "منحُ دور secretary صلاحيّةَ STAFF_AFFAIRS_MANAGE",
        "",
        "دورُ secretary يحمل صلاحيّةَ STAFF_AFFAIRS_MANAGE اللازمة لعمله الفعليّ؛ اختبارٌ يثبت وصولَه بعد المنح.",
        "done",
        100,
        D(2026, 10, 1),
        DAY,
        "W-20261001-026، نُشر main@3b615dc5 (2026-10-01)",
        0.5,
        "",
        "#758",
        "",
        "**بندٌ جديدٌ بقاعدة الإدراج (إصلاحُ صلاحيّاتٍ/RBAC).**",
        778,
    ),
    (
        "N-056",
        "N",
        "backend",
        "وصفُ المخالفة السلوكيّة يصير اختياريّاً بلا استثناء",
        "",
        "حقلُ وصف المخالفة السلوكيّة اختياريٌّ في كلّ مسارات الإدخال بلا استثناءٍ متبقٍّ (SOS-20260930-E132).",
        "doing",
        90,
        D(2026, 10, 1),
        None,
        "W-20261001-003، دُمج main@8358add3 (2026-10-01)، بإفادة «0101 · المايسترو» عبر «0201 · أمين البلاغات»",
        0.5,
        "",
        "#752",
        "",
        "**بندٌ جديدٌ بقاعدة الإدراج.** **دُمج ولم يُنشر تأكيداً بعد** — أمينُ البلاغات صرّح بعدم تحقّقه من النشر الفعليّ؛ يبقى doing حتى يصل تأكيدٌ مباشر فيُغلَق done.",
        779,
    ),
    (
        "N-057",
        "N",
        "backend",
        "استيرادُ سجلّ القيد الوزاريّ (26 عموداً) — القالبُ المعتمَد",
        "",
        "استيرادُ ملفّ سجلّ القيد الوزاريّ الحقيقيّ (26 عموداً) بلا أخطاء؛ المالكُ يتحقّق مباشرةً من الحساب والترفيع/التسجيل الدراسيّ والسجلّ الصحّيّ لطالبٍ تجريبيّ ثمّ يحذفه.",
        "done",
        100,
        D(2026, 10, 1),
        DAY,
        "W-20261001-029، نُشر main@7000b976 (2026-10-01)",
        3.0,
        "",
        "#750",
        "core/ministry_import.py",
        "**بندٌ جديدٌ بقاعدة الإدراج.** **قياسٌ حقيقيٌّ:** 734 صفّاً من الملفّ الوزاريّ الحقيقيّ، 0 أخطاء، 0.68-0.95 ثانية (بعد إصلاح أداءٍ من 46.65 ثانية الأصليّة)، 10 استعلامات. "
        "المالكُ تحقّق فعليّاً على 8500 بطالبٍ تجريبيّ حقيقيّ ثمّ حذفه. قراراتٌ منفَّذة: إهمالُ عمودي قطاع/جهة العمل الأوّلين (ميّتان دائماً)، لا حاجةَ لعمود المسار الدراسيّ، وقبولُ طبقاتٍ صريحٌ core→clinic معتمَدٌ من المالك (tests/layering_baseline.json).",
        780,
    ),
    (
        "N-058",
        "N",
        "backend",
        "إصلاحُ «إرسال نسخة» — لا يُسقَط على أنّه إرسالٌ رسميّ للمعلّم",
        "",
        "زرُّ «إرسال نسخة» لا يُعامَل في السجلّات والإشعارات معاملةَ الإرسال الرسميّ الموجَّه للمعلّم.",
        "done",
        100,
        D(2026, 10, 1),
        DAY,
        "W-20261001-004، نُشر main@e75185ed (2026-10-01)",
        0.5,
        "",
        "#749",
        "",
        "**بندٌ جديدٌ بقاعدة الإدراج (إصلاحٌ صغير).**",
        781,
    ),
    (
        "N-059",
        "N",
        "frontend",
        "هويّةٌ بصريّةٌ كاملةٌ لصفحة «غير متصل»",
        "",
        "صفحةُ «غير متصل» (offline) بهويّةٍ بصريّةٍ كاملةٍ تطابق هويّةَ المنصّة، لا صفحةَ متصفّحٍ افتراضيّة.",
        "done",
        100,
        D(2026, 10, 1),
        DAY,
        "W-20261001-047، نُشر main@b75279eb (2026-10-01)",
        1.0,
        "",
        "#764",
        "",
        "**بندٌ جديدٌ بقاعدة الإدراج.**",
        782,
    ),
]

# (الرمز، (القيمة الحاليّة، تاريخ القياس) المتوقَّعان، القيمة الجديدة، تاريخُ القياس الفعليّ، مرجعُ القياس يُلحق بمصدر المؤشّر)
KPI_UPDATES = [
    (
        "V-K01",
        (275398.0, D(2026, 9, 28)),
        272763.0,
        D(2026, 10, 1),
        "0702، بوّابةُ الجودة main@4c7e095b، 2026-10-01: CSS المشحون 272,763 من سقف 275,456 (269KB)، الهامشُ 2,693 بايتاً بعد #751",
    ),
    (
        "PK6",
        (1247.0, D(2026, 9, 29)),
        1247.0,
        D(2026, 10, 1),
        "0702، بوّابةُ الجودة main@4c7e095b، 2026-10-01: إعادةُ تأكيدٍ — 1247 خطأً في 121 ملفّاً، ثابتٌ عن 29-09",
    ),
]

KPI_WHY_NOTES: list[tuple[str, str]] = []


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


def sync_kpi_notes(kpi_model):
    """تُلحق سطراً بحقل «لماذا» في مؤشّرٍ قائم مرّةً واحدة؛ لا تلمس قيمتَه؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, line in KPI_WHY_NOTES:
        kpi = kpi_model.objects.filter(code=code).first()
        if kpi is None or line in kpi.why:
            continue
        kpi.why = f"{kpi.why}\n{STAMP} {line}".strip()
        kpi.save(update_fields=["why", "updated_at"])
        changed.append(code)
    return changed


def forwards(apps, schema_editor):
    item_model = apps.get_model("roadmap", "RoadmapItem")
    # قاعدةٌ بلا استيراد (اختبار، شجرةٌ جديدة): لا شيء يُزامَن، ولا بنودٌ يتيمة.
    if not item_model.objects.exists():
        return
    kpi_model = apps.get_model("roadmap", "RoadmapKpi")
    sync(item_model)
    add_new_items(item_model)
    sync_kpi_values(kpi_model)
    sync_kpi_notes(kpi_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0044_sync_items_2026_09_29"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
