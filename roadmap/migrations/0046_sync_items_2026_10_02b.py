"""الخارطةُ الثالثةُ والثلاثون (2026-10-02): نشرُ 2/10 — ADR-0009 (فصلُ دلالة الحضور واستبعادُ platform_developer)، تبويبُ رسائل المطوّر،
إلغاءُ حركة بطاقة الدخول، إصلاحُ VI-13 الجذريّ، ومقاييسُ mypy وCSS الحقيقيّة.

حارسةٌ كسابقاتها: لا يُلمس بندٌ إلّا إن طابقت حالتُه وتقدّمُه (أو مؤشّرٌ: قيمتُه وتاريخُ قياسه) آخرَ لقطة، ولا تُكرَّر ملاحظةٌ، ولا بندَ يُغلق بلا قياسٍ.

**N-056 يُغلق** لأنّ #752 سلفٌ للإيداع المنشور على الإنتاج (تحقّقٌ بغيت، لا بإفادةٍ فقط).
**VI-13:** ملاحظةٌ فقط (بلا لمس حالته ولا تقدّمه) — #770 أصلحَ سببَ فشل حارس اللقطات في صفحة الأجنحة (عنصرا الوقت الحيّ)، لكنّ فعاليّتَه على الطلبات المفتوحة العابرة لمنتصف الليل لم تُقَس بعد.

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
        "N-056",
        ("doing", 90),
        "done",
        100,
        "",
        "**نُشر فعلاً:** #752 (main@8358add3) سلفٌ للإيداع 3cbcfb6a المنشور على الإنتاج (تحقّقٌ بغيت، وتأكيدٌ مباشرٌ من جلسة النشر) — وصفُ المخالفة السلوكيّة اختياريٌّ حيّاً.",
    ),
    (
        "N-059",
        ("done", 100),
        "done",
        100,
        "#769",
        "**#769 نُشر main@6939d8db (2026-10-02):** تفعيلُ الهويّة البصريّة الكاملة (ترويسةُ بطاقة الدخول والذيلُ المركزيّ) في صفحات الأخطاء 403 و404 وforbidden وno_membership؛ استُثنيت 500.html عمداً (قد تُعرض حين يعجز الخادمُ عن خدمة ملفّات الأنماط). 52 اختباراً خضراء.",
    ),
    (
        "SCH-22",
        ("doing", 15),
        "doing",
        15,
        "#768 #773",
        "**#768 (تصحيحُ AS-3 العاجل) و#773 (قسمُ سقف الحمل اليوميّ: قائمٌ أصلاً قيداً صلباً HC16) نُشرا (main@6123bee، 2026-10-02):** تصحيحاتٌ وثائقيّةٌ في constraints_spec.html — لا شيفرةَ ولا هجرة، فالتقدّمُ 15% كما هو.",
    ),
]

# ملاحظاتٌ على بنودٍ قائمة تُلحق مرّةً واحدة بلا لمس الحالة ولا التقدّم (حالتُها المحلّيّةُ قد تختلف عن الإنتاج)
NOTES = [
    (
        "VI-13",
        "**#770 نُشر main@ad8d8dcb (2026-10-02، W-20261001-030):** السببُ الجذريّ لفشل حارس اللقطات في wing_supervisor--wings_floors: عنصران يعتمدان وقتَ الطلب (ساعةُ الترويسة وحالةُ «الآن» لكلّ حصّة) — غُطّيا بـdata-visual-mask الموجودة بنيتُها أصلاً. "
        "لقطاتُ main نجحت بعد #770 وفي أربعة تشغيلاتٍ سابقةٍ له. **لم تُقَس بعدُ فعاليّتُه على الطلبات المفتوحة العابرة لمنتصف الليل بأساسٍ قديم (يرصدها 0702 لاحقاً)** — فلا تقدّمَ يُحتسب بها.",
    ),
]

# بنودٌ جديدة: (الرمز، المصدر، المسار، العنوان، الاعتماديّات، المعيار، الحالة، التقدّم، البداية، النهاية، أساسُ التاريخ، الجهد، البوّابة، طلب الدمج، المرجع، الملاحظة، الترتيب)
NEW_ITEMS = [
    (
        "N-060",
        "N",
        "backend",
        "ADR-0009: فصلُ دلالة الحضور عن الغياب الوزاريّ واستبعادُ platform_developer من شاشات التحليلات",
        "",
        "attendance_rate() لا يُسمّى غيابَ المدرسة الوزاريّ في أيّ شاشة (مصدرٌ مستقلٌّ للغياب الوزاريّ)؛ /analytics/api/* محروسةٌ بالقدرة؛ دورُ platform_developer مستبعَدٌ صراحةً من اثنتي عشرة شاشة؛ حارسُ ارتدادٍ يمنع تسميةَ معدّلٍ على مستوى الحصّة غياباً.",
        "done",
        100,
        D(2026, 10, 1),
        DAY,
        "W-20261001-039 و040 و043، نُشر main@3cbcfb6a (2026-10-02)؛ قرارُ المالك D-98م",
        3.0,
        "",
        "#762 #767",
        "ADR-0009",
        "**بندٌ جديدٌ بقاعدة الإدراج (يضمّ ثلاثَ بطاقاتٍ في طلبٍ واحد):** #767 وثّق ADR-0009 (تحقيقٌ ميدانيٌّ أثبت خلطاً جزئيّاً بين الغياب اليوميّ الوزاريّ وتواجد الحصص، وخمسَ مخالفاتٍ في عرض الصلاحيّات). "
        "#762 نفّذ: W-039 (فصلُ attendance_rate() عن الغياب الوزاريّ، ومصدرٌ جديدٌ DailyReport.ministry_absent_count، وتسميتان مصحَّحتان)، W-040 (فحصٌ أمنيٌّ: /analytics/api/* محروسةٌ بالقدرة حيّاً، لا ثغرةَ فيها)، "
        "W-043 (قرارُ المالك D-98م: استبعادُ platform_developer صراحةً عبر core.permissions_deny.deny_role على 12 شاشة). **المقيس:** 171 اختباراً ناجحاً مع اختبارَي استبعادٍ جديدين، وحارسُ الارتداد نجح في بوّابة الجودة؛ "
        "وأساسُ mypy نزل 1247 ← 1221 (مقيسٌ من 0702، انظر PK6).",
        783,
    ),
    (
        "N-061",
        "N",
        "frontend",
        "إلغاءُ حركة دخول بطاقة صفحة الدخول",
        "",
        "بطاقةُ صفحة الدخول تظهر ثابتةً فوراً بلا حركة دخول؛ حارسٌ يمنع عودةَ الحركة بأيّ صيغة.",
        "done",
        100,
        D(2026, 10, 1),
        DAY,
        "بأمر المالك المباشر، نُشر ضمن main@55b175ec (2026-10-02)",
        0.5,
        "",
        "#765",
        "",
        "**بندٌ جديدٌ بقاعدة الإدراج.** أُزيلت loginCardIn وكلُّ ما يرافقها؛ وحُوّل حارسُ الأداء إلى test_the_login_card_has_no_entrance_animation. 11 اختباراً خضراء ومعاينةٌ بصريّةٌ تؤكّد زوالها.",
        784,
    ),
    (
        "N-062",
        "N",
        "backend",
        "تبويبُ «رسائل المطوّر» المستقلّ وبثُّ المطوّر للمستخدمين",
        "",
        "تبويبٌ مستقلٌّ «رسائل المطوّر» في الشريط الرئيسيّ (صندوقُ الوارد والجديدة وما أُرسل)؛ المطوّرُ يبثّ رسالةً لفردٍ أو قسمٍ أو دورٍ أو الجميع عبر الإشعارات القائمة بنوع حدثٍ developer_message، بعدّاد مستلِمين حيّ وتأكيدٍ قبل البثّ الواسع.",
        "done",
        100,
        D(2026, 9, 30),
        DAY,
        "W-20261001-036، نُشر main@55b175ec (2026-10-02)؛ طلبُ المالك 2026-09-30",
        4.0,
        "",
        "#761",
        "",
        "**بندٌ جديدٌ بقاعدة الإدراج (لا بندَ قائمٌ يغطّيه).** نموذجٌ خفيفٌ OutboundMessage لسجلّ المطوّر فقط، والتسليمُ عبر notifications.InAppNotification — لا صندوقَ واردٍ موازياً. **بهجرتين:** developer_feedback 0004 وnotifications 0018. "
        "**ليس MAE-14:** اتّجاهُه معاكس (من المطوّر إلى المستخدمين)، أمّا MAE-14 فرسائلُ إلى المالك بدرجات خطورةٍ ومهلة — لم يُبنَ بعد. "
        "اختباراتٌ تغطّي resolve_recipients وview الإرسال (403 لغير المطوّر).",
        785,
    ),
]

# (الرمز، (القيمة الحاليّة، تاريخ القياس) المتوقَّعان، القيمة الجديدة، تاريخُ القياس الفعليّ، مرجعُ القياس يُلحق بمصدر المؤشّر)
KPI_UPDATES = [
    (
        "V-K01",
        (272763.0, D(2026, 10, 1)),
        272619.0,
        D(2026, 10, 2),
        "0702، بوّابةُ الجودة main@3cbcfb6a، 2026-10-02: CSS المشحون 272,619 من سقف 275,456، الهامشُ 2,837 بايتاً",
    ),
    (
        "PK6",
        (1247.0, D(2026, 10, 1)),
        1221.0,
        D(2026, 10, 2),
        "0702، بوّابةُ الجودة main@3cbcfb6a، 2026-10-02: 1,221 خطأً في 122 ملفّاً (مقيسٌ لا من السجلّ)، بعد #762",
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


def forwards(apps, schema_editor):
    item_model = apps.get_model("roadmap", "RoadmapItem")
    # قاعدةٌ بلا استيراد (اختبار، شجرةٌ جديدة): لا شيء يُزامَن، ولا بنودٌ يتيمة.
    if not item_model.objects.exists():
        return
    kpi_model = apps.get_model("roadmap", "RoadmapKpi")
    sync(item_model)
    sync_notes(item_model)
    add_new_items(item_model)
    sync_kpi_values(kpi_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0045_sync_items_2026_10_02"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
