"""الخارطةُ السادسةُ والثلاثون (2026-10-02): تسريعُ CI، وإيقاعُ تطبيق المعاينة 8500، وسدُّ فجواتٍ قديمةٍ كشفتها مقابلةُ المدموج بالخارطة.

حارسةٌ كسابقاتها: لا تُكرَّر ملاحظةٌ، ولا يُنشأ بندٌ موجود، ولا بندَ يُغلق بلا قياسٍ أو مرجع.

**ملاحظةٌ منهجيّة:** لوحةُ «مزامنةُ الخارطة» (MAE-11) تعدّ الطلبَ «غيرَ مُزامَن» ما لم يرد رقمُه في pr/note/ref بند — فتُذكر هنا طلباتُ هجراتِ الخارطة نفسِها
(بلا لمس حالةِ أيّ بند) كي لا تُنذر اللوحةُ بها أبداً، وطلباتٌ أقدمُ لم يُذكر رقمُها (#691 #692 #693 #694).

**ما لم يُقَس لا يُحتسب:** N-071 وN-072 يبقيان doing لبقاء قياسٍ لم يتمّ (merge_group؛ فجوةُ ظهور الإيداع بعد أوّل تطبيق).

والمستودعُ عامّ: نصوصٌ محايدة.
"""

import datetime

from django.db import migrations

STAMP = "[2026-10-02]"
D = datetime.date
DAY = D(2026, 10, 2)

# ملاحظاتٌ على بنودٍ قائمة تُلحق مرّةً واحدة بلا لمس الحالة ولا التقدّم: (الرمز، السطر)
NOTES = [
    (
        "SCH-23",
        "**#789 دُمج main@e9023d69 (2026-10-02، W-20261002-033):** تسريعُ اختبار عدّاد المخالفات الصلبة (tests/test_hard_violations_single_source.py) — **2.3 ثانية بدل 289 بحسب عنوان الطلب (قياسُ جلسة التنفيذ لا قياسي)**. "
        "يخصّ تحليلَ عنق pytest بعد #777 (اختبارٌ واحدٌ أضافه #777 بحسب جلسة التحليل 0408)؛ **أثرُه على مدّة بوّابة الجودة الكاملة لم يُقَس بعدُ**.",
    ),
    (
        "N-069",
        "**#794 دُمج main@18bd513d (2026-10-02، W-20261002-030 الجزء ج):** نصّا CLAUDE.md «لا دفعَ قبل نجاح make prepush» و«ادفع فورَ اعتماد المالك» (ومعهما تصحيحُ تثبيت 8500 وفتحِ الطلبات، وتطبيقُ 8500 الإجباريّ). "
        "**يبقى من W-20261002-030 الجزء (ب): shards لـpytest — لم يُنجز.** زمنُ prepush المقيس في الطلب: 14 ثانيةً على ملفٍّ واحد.",
    ),
    (
        "REP-10",
        "**#693 دُمج (2026-09-26):** سباقُ ملفّ القفل في تجهيزات اختبار الأداة — لا صيانةَ خلفيّةً في المستودع العابر؛ وهو من تتمّة REP-10 قبل انتقاله إلى QCC.",
    ),
    (
        "MAE-11",
        "**طلباتُ هجراتِ الخارطة نفسِها تُذكر هنا (بلا لمس الحالة) لئلّا تُنذر اللوحةُ بها:** #690 #695 #712 #721 #755 #771 #778 #780 #792. وقد كشفت مقابلةُ المدموج بالخارطة بعد هذه اللوحة أرقاماً فاتت يدويّاً (#744 #751 #735 #730 #737) — فاللوحةُ تؤدّي جوهرَها.",
    ),
]

# بنودٌ جديدة: (الرمز، المصدر، المسار، العنوان، الاعتماديّات، المعيار، الحالة، التقدّم، البداية، النهاية، أساسُ التاريخ، الجهد، البوّابة، طلب الدمج، المرجع، الملاحظة، الترتيب)
NEW_ITEMS = [
    (
        "N-071",
        "N",
        "ops",
        "تسريعُ بوّابة CI: حَكَمٌ مشتركٌ صارم وfast-guards وطلبٌ وثائقيٌّ بلا تغطية",
        "",
        "الحرّاسُ النصّيّةُ السريعة تفشل مبكّراً بلا قاعدة؛ طلبٌ وثائقيٌّ (.md تحت docs/ وAAdocs/ فقط) يُجري «قرّاءَ الوثائق» بلا تغطية؛ scripts/ci_needs_gate.py: كلُّ needs يساوي success وإعفاءُ skipped لـpush فقط وفشلٌ مغلق؛ والسياقان المطلوبان ثابتان؛ وسياقُ الأمن بلا أيّ إعفاء.",
        "doing",
        90,
        D(2026, 10, 1),
        None,
        "W-20261002-031 (P1)، دُمج main@1c53d481 (2026-10-02)",
        2.0,
        "",
        "#786",
        "",
        "**بندٌ جديدٌ بقاعدة الإدراج (لا بندَ قائمٌ يغطّيه).** **المقيس (طلبان تجريبيّان أُغلقا بلا دمج #790 و#791، وقياسُ 0105 بـgh api):** طلبٌ وثائقيٌّ pytest 6.5 دقيقةً مقابل 22.1 للكود؛ fast-guards نحو 1.5 دقيقة؛ السياقان ناجحان على pull_request؛ إعفاءاتُ push (mypy وaxe-a11y وe2e فقط) تعمل. "
        "**ما بقي (فلا done):** merge_group لم يُقَس بعدُ (عند 0105)؛ W-20261002-032 (CODEOWNERS لـ.github/** وscripts/ci_*.py وtests/test_ci_*.py، P2) بطاقةٌ مفتوحة؛ ملاحظةُ 0105 P3 (مسارٌ نسبيّ في test_security_gate)؛ وإعفاءُ Security Scan على push مؤجَّلٌ لقراءة المالك إعدادَ Railway «Wait for CI». خريطةُ الحرّاس حُدِّثت في الطلب نفسه.",
        796,
    ),
    (
        "N-072",
        "N",
        "ops",
        "المعاينة 8500: تطبيقٌ إجباريٌّ كلَّ 10 دقائق وحدُّ تثبيتٍ 30 دقيقةً وطابورُ انتظار",
        "",
        "إن وُجد جديدٌ وانقضت 600 ثانيةً على آخر تطبيقٍ طُبّق ولو لم يهدأ شيء؛ حدُّ التثبيت 30 دقيقةً بالقصّ لا الرفض ويُفكّ آليّاً؛ من يُرفض تثبيتُه يدخل طابورَ انتظارٍ يُثبَّت آليّاً بالترتيب؛ سجلُّ تطبيقاتٍ apply.log وأمرُ preview.sh gaps يقيس فجوةَ ظهور كلّ إيداع.",
        "doing",
        90,
        D(2026, 10, 2),
        None,
        "W-20261002-029، دُمج main@1c3ed4db (2026-10-02)؛ قرارُ المالك 2026-10-02",
        2.0,
        "",
        "#788",
        "D-143م",
        "**بندٌ جديدٌ بقاعدة الإدراج (لا بندَ قائمٌ يغطّيه).** 31 اختباراً جديداً بمصدرٍ في مستودعٍ مؤقّت (بلا docker ولا شبكة). **«قبل» (≈15 دقيقة) حدٌّ نظريٌّ من الإعداد القديم لا قياس؛ والقياسُ الفعليّ لفجوة الظهور يبدأ من أوّل تطبيقٍ بعد التحديث (لا قياسَ رجعيّاً)** — فلا done قبل أن يصل قياسُ gaps. "
        "لم يُلمس سطرُ الاعتماد بالإيداع (قرارُ فلو عند 0103 و0601 لاحقاً).",
        797,
    ),
    (
        "N-073",
        "N",
        "ops",
        "المعاينة المركزيّة 8500: التكاملُ (يضمّ رؤوسَ الطلبات المفتوحة) والفلو الجديد في CLAUDE.md",
        "",
        "الخادمُ المقيمُ 8500 يعرض main وما أودعته الجلساتُ ولم يُدمج (بعد رؤوس الأشجار رؤوسُ الطلبات المفتوحة غيرِ المسوّدة وغيرِ الآليّة)؛ وCLAUDE.md يصف الفلو: معاينةُ المالك واعتمادُه قبل كلّ دفع.",
        "done",
        100,
        D(2026, 9, 26),
        DAY,
        "#691 #692 #694 دُمجت 2026-09-26؛ قائمةٌ حيّاً بحسب CLAUDE.md وdocs/deployment/local_preview.md",
        2.0,
        "",
        "#691 #692 #694",
        "",
        "**بندٌ جديدٌ بقاعدة الإدراج (يسدّ فجوةً قديمةً كشفتها مقابلةُ المدموج بالخارطة؛ دُمجت قبل أيّام ولم يُذكر رقمُها).** أدواتُ جلساتٍ لا ميزةُ إنتاج؛ لا قياسَ لها هنا سوى وجودِها في CLAUDE.md الحاليّ. "
        "تعدّلت لاحقاً: #784 و#788 و#794.",
        798,
    ),
]

# (الرمز، (القيمة الحاليّة، تاريخ القياس) المتوقَّعان، القيمة الجديدة، تاريخُ القياس الفعليّ، مرجعُ القياس يُلحق بمصدر المؤشّر)
KPI_UPDATES = [
    (
        "V-K01",
        (272619.0, D(2026, 10, 2)),
        273053.0,
        D(2026, 10, 2),
        "0702، بوّابةُ الجودة main@416e9612، 2026-10-02: CSS المشحون 273,053 من سقف 275,456، الهامشُ 2,403 بايتاً (يضيق مع كلّ ميزة واجهة)",
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
        ("roadmap", "0048_sync_items_2026_10_02d"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
