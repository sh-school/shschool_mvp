"""الخارطةُ الثامنةُ والثلاثون (2026-10-03): نشرُ d67809f و0e78749 — تشفيرُ تاريخ الميلاد (التوسيع)، وإلغاءُ استبعاد platform_developer، ونصابُ اللجنة،
وساعةُ المولّد، وقائمةُ المغادرين، وتقصيرُ CLAUDE.md؛ وتصحيحُ دقّةِ نشرِ #793؛ ومقاييسُ mypy وCSS الحقيقيّة.

حارسةٌ كسابقاتها: لا تُكرَّر ملاحظةٌ، ولا يُنشأ بندٌ موجود، ولا بندَ يُغلق بلا قياسٍ أو نشرٍ مؤكَّد.

**N-060:** استبعادُ platform_developer الذي سُجّل إنجازاً في 0046 أُلغي بعد ذلك (D-118م، المسجَّل في دفتر القرارات، ونصُّ #781) — ملاحظةٌ تصحّح الصورة.
**N-076:** مرحلةُ التوسيع فقط؛ الملءُ على الإنتاج بيد المالك ثمّ التحقّق — فبوّابةُ owner لا done.
**QCC-09:** نُشر، لكنّ المعاينةَ البصريّة لم تصل — تبقى doing.

والمستودعُ عامّ: نصوصٌ محايدة بلا تفاصيل ثغراتٍ ولا بياناتٍ شخصيّة.
"""

import datetime

from django.db import migrations

STAMP = "[2026-10-03]"
D = datetime.date
DAY = D(2026, 10, 3)

# ملاحظاتٌ على بنودٍ قائمة تُلحق مرّةً واحدة بلا لمس الحالة ولا التقدّم: (الرمز، السطر)
NOTES = [
    (
        "N-060",
        "**تصحيحُ الصورة (2026-10-03):** #781 (main@d67809fa، W-20261002-012) ألغى استبعادَ platform_developer الوارد في هذا البند — «لا حظرَ على platform_developer في أيّ صفحة» بقرار المالك D-118م (يُلغي D-98م، "
        "ثمّ D-123م لواجهات API؛ المسجَّلان في دفتر القرارات). فمعيارُ «مستبعَدٌ صراحةً من اثنتي عشرة شاشة» لم يَعُد قائماً في الشيفرة؛ وما بقي: فصلُ attendance_rate() عن الغياب الوزاريّ (W-039) والفحصُ الأمنيّ (W-040).",
    ),
    (
        "N-074",
        "**تصحيحُ دقّةِ النشر:** #793 ظهر أوّلاً على be7df53 في 2026-10-02 (لا bd0c8d6 كما كُتب في أساس التاريخ؛ bd0c8d6 هو الأحدثُ الذي يحويه) — بإفادة جلسة النشر من /health/.",
    ),
    (
        "QCC-09",
        "**#787 نُشر main@d67809f (2026-10-03، تأكيدٌ مباشرٌ من جلسة النشر).** **المعاينةُ البصريّةُ على الإنتاج لم تصلني بعدُ** — فلا done. القياسان المصاحبان (0702 على d67809fa): هامشُ CSS 2,345 بايتاً، وصفحاتٌ بلا نمط تخطيط 135.",
    ),
    (
        "N-068",
        "**#804 نُشر main@d67809f (2026-10-03، W-20261003-001):** تثبيتُ ساعة رصد اختبار لوحة السكرتير على 09:30 فلا يسقط من منتصف الليل حتى 06:30 بتوقيت الدوحة (كان يُسقط فحصَ طلبٍ ليلاً دون علّةٍ في الشيفرة). إصلاحٌ في الاختبار وحدَه.",
    ),
    (
        "SCH-21",
        "**#798 نُشر main@d67809f (2026-10-03، W-20261002-033 ب):** ساعةٌ داخل محاولة التوليد (budget_cut) ومحاولةٌ واحدة عند نفاد الميزانية، والمتعذّراتُ شرطُ إقرارٍ صريحٍ للاعتماد (يُسمّيه الطلبُ «OR-01، قرارُ المالك»)، وتقسيمُ scheduler.py بلا تغيير سلوك — يُسجَّل في SCH-25. "
        "**لا أُغلق G6 ولا أسجّل حكماً للمالك على «هل تُعتمد مسوّدةٌ فيها متعذّر؟»:** لم يصلني حكمُه مباشرةً؛ وصفُ الطلب نفسُه لا يكفي.",
    ),
]

# بنودٌ جديدة: (الرمز، المصدر، المسار، العنوان، الاعتماديّات، المعيار، الحالة، التقدّم، البداية، النهاية، أساسُ التاريخ، الجهد، البوّابة، طلب الدمج، المرجع، الملاحظة، الترتيب)
NEW_ITEMS = [
    (
        "N-076",
        "N",
        "security",
        "تشفيرُ تاريخ ميلاد الطلبة (PDPPL): مرحلةُ التوسيع ثمّ الملءُ ثمّ حذفُ القديم",
        "N-066",
        "Profile.birth_date_encrypted بكتابةٍ مزدوجة وقراءةٍ عبر date_of_birth؛ أمرُ backfill_birth_date_encrypted يُنفَّذ على الإنتاج ثمّ --verify يطابق؛ **ثمّ** (إصدارٌ لاحق) حذفُ العمود القديم.",
        "doing",
        50,
        D(2026, 10, 1),
        None,
        "W-20261001-016، نُشر main@d67809f (2026-10-03، مرحلة التوسيع)؛ توسيعٌ ثمّ تقليص (P4-1)",
        3.0,
        "owner",
        "#799",
        "0105 M1-M3",
        "**بندٌ جديدٌ بقاعدة الإدراج (من المراجعة الرجعيّة للامتثال).** نُفِّذ: العمودُ المشفَّر والكتابةُ المزدوجة وأمرُ الملء (core هجرة 0077) وشروطُ 0105 M1-M3، واختبارات tests/test_profile_birth_date_encryption.py. "
        "**المتبقّي: الملءُ على الإنتاج بيد المالك ثمّ --verify، ثمّ حذفُ القديم في إصدارٍ لاحق** — فالبوّابةُ owner والتقدّمُ 50% اشتقاقٌ لا قياس (لا أرقامَ ملءٍ على الإنتاج بعد).",
        802,
    ),
    (
        "N-077",
        "N",
        "backend",
        "الصلاحيّات: لا حظرَ على platform_developer (D-118م/D-123م) ونصابُ لجنة الضبط (W-024)",
        "N-060",
        "platform_developer يمرّ كلَّ بوّابات الصفحات وواجهاتِ API (مع تدقيقٍ فقط لصفحات حسّاسة بحسب D-123م) فيما تُحفظ استثناءاتُ المالك الصريحة؛ ونصابُ لجنة الضبط في committee_services: أغلبيةٌ مؤهَّلة بلا تفويض ويُستبعد المُبلِّغ من الأعضاء المؤهَّلين.",
        "done",
        100,
        D(2026, 10, 2),
        DAY,
        "W-20261002-012 و024، نُشر main@d67809fa (2026-10-03)؛ قراراتُ المالك D-118م وD-123م",
        4.0,
        "",
        "#781",
        "D-118م · D-123م",
        "**بندٌ جديدٌ بقاعدة الإدراج (مسارُ صلاحيّاتٍ واسع: 45 ملفّاً في الطلب — حُكمُ 0105 الاستشاريّ لم يصلني فلا أنسبه إليها).** يُلغي استبعادَ D-98م المسجَّل في N-060. "
        "اختباراتٌ جديدة: test_committee_quorum وtest_developer_reaches_every_page وtest_platform_developer_unrestricted. يحمل الطلبُ أيضاً إيداعاتٍ مكدَّسةً سبق تسجيلُها (#762 وغيرها).",
        803,
    ),
    (
        "SCH-25",
        "SCH",
        "backend",
        "ساعةُ محاولة المولّد وبوّابةُ المتعذّرات: قطعُ الميزانية وإقرارٌ صريحٌ للاعتماد",
        "SCH-21",
        "ساعةٌ داخل محاولة التوليد تقطع الميزانيّةَ بمحاولةٍ واحدة؛ وجدولٌ فيه حصّةٌ متعذّرةٌ لا يُعتمد إلّا بإقرارٍ صريحٍ يُحكم فيه على الخادم؛ وعند نفاد الميزانية يُذكر أنّ المتعذّر قد يكون من قطعٍ لا من استحالة.",
        "doing",
        60,
        D(2026, 10, 1),
        None,
        "W-20261002-033 (ب)، نُشر main@d67809f (2026-10-03)",
        3.0,
        "",
        "#798",
        "OR-01",
        "**بندٌ جديدٌ بقاعدة الإدراج (عائلةُ SCH-، ابنٌ لـSCH-21).** نصُّ الطلب يسمّي شرطَ الإقرار «OR-01، قرارُ المالك» — **لم يصلني تأكيدٌ مباشرٌ فلا أسجّله قراراً**. تقسيمُ scheduler.py إلى scheduler_clock وscheduler_advice بلا تغيير سلوك. "
        "**التقدّم 60% اشتقاقٌ (الجزءُ «ب» من W-033؛ باقي الأجزاء غيرُ معروفةٍ لي)، ولا قياسَ إنتاجيَّ لأثر ساعة المحاولة بعد.**",
        804,
    ),
    (
        "N-078",
        "N",
        "backend",
        "شؤون الموظّفين: «المغادرون» من لا عضويّةَ كادرٍ نشطةً له، والمغادرةُ بدورٍ محدَّد",
        "",
        "قائمةُ المغادرين تضمّ من لا عضويّةَ كادرٍ نشطةً له (لا من له صفٌّ منتهٍ قديمٌ وهو على رأس عمله)؛ وstaff_depart لمن له أكثرُ من دورٍ تُتيح دوراً بعينه أو «كلَّ أدواره».",
        "done",
        100,
        D(2026, 10, 2),
        DAY,
        "W-20261002-043، ظهر أوّلاً على الإنتاج بالإيداع bde41f1 (2026-10-03)",
        1.0,
        "",
        "#803",
        "",
        "**بندٌ جديدٌ بقاعدة الإدراج.** قراءاتُ الكادر نُقلت إلى selectors كي لا تنمو العروضُ فوق سقّاطة الطبقات؛ وخيارُ الدور المغادَر حقلٌ في النموذج. **ظهرَ أوّلاً على الإنتاج بالإيداع bde41f1 (رصدتْه جلسةُ النشر بـ/health/ قبل ظهور 0e78749 الذي يحويه).**",
        805,
    ),
    (
        "N-079",
        "N",
        "ops",
        "تقصيرُ CLAUDE.md إلى 142 سطراً وقواعدُ .claude/rules بالمسار",
        "N-070",
        "CLAUDE.md بـ142 سطراً، والقواعدُ التفصيليّة في .claude/rules بحسب المسار.",
        "doing",
        90,
        D(2026, 10, 3),
        None,
        "W-20261003-006، دُمج main@73d848c8 (2026-10-03) ولم يُنشر",
        1.0,
        "",
        "#806",
        "",
        "**بندٌ جديدٌ بقاعدة الإدراج (وثائقيّ).** مدموجٌ ولم يؤكَّد نشرُه — يُغلق done بإشعار جلسة النشر. يحمل الطلبُ إيداعاتٍ مكدَّسةً سبق تسجيلُها (#784 و#788 و#794).",
        806,
    ),
]

# (الرمز، (القيمة الحاليّة، تاريخ القياس) المتوقَّعان، القيمة الجديدة، تاريخُ القياس الفعليّ، مرجعُ القياس يُلحق بمصدر المؤشّر)
KPI_UPDATES = [
    (
        "V-K01",
        (273053.0, D(2026, 10, 2)),
        273111.0,
        D(2026, 10, 3),
        "0702، tests.css_source.shipped_size() في حاوية بلا شبكة على main@d67809fa، 2026-10-03: 273,111 من سقف 275,456، الهامش 2,345 بايتاً",
    ),
    (
        "PK6",
        (1221.0, D(2026, 10, 2)),
        1219.0,
        D(2026, 10, 3),
        "0702، خطوة «فحص الأنواع» في بوّابة الجودة على main@d67809fa، 2026-10-03: 1,219 خطأً في 122 ملفّاً",
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
            pr=_add_pr("", pr),
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
    sync_notes(item_model)
    add_new_items(item_model)
    sync_kpi_values(kpi_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0050_sync_items_2026_10_03"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
