"""الخارطةُ الأربعون (2026-10-03): نشرُ 3b70242 — اتّساعُ حماية بيانات المحو (#805 #810)، وحرّاسُ CI الجديدة (#807)، وتخطيطُ سجلّ الكادر (#809، مدموجٌ بلا نشر)،
وهامشُ CSS الذي يضيق، وسدُّ إشارة طلبات الخارطة نفسِها في لوحة المزامنة.

حارسةٌ كسابقاتها: لا تُكرَّر ملاحظةٌ، ولا يُنشأ بندٌ موجود، ولا بندَ يُغلق بلا قياسٍ أو نشرٍ مؤكَّد.

**N-081 (#809):** مدموجٌ ولم يُنشر → doing لا done.
**V-K01:** قياسُ 0702 بأداة shipped_size()؛ الهامشُ يضيق على أربع نشرات متتالية فيقترب من حدّ التحذير.

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
        "N-075",
        "**امتدادٌ بطلبَين نُشرا (2026-10-03):** #805 (main@fd9066c3، W-20261002-040) حصرُ عروض المحو بمدرسة المدير وفحصُ عضويّة الطالب (وولّي الأمر) عند الإنشاء ودفاعٌ في العمق في ErasureService؛ "
        "و#810 (main@b7c426a3، W-20261002-042) حارسُ المحو يشمل كلَّ علاقةٍ بالمستخدم وحقولَ المستلم/الهاتف، ومسحُ نصوص NotificationEnqueueIntent وحذفُ DeveloperMessage عند المحو (بشرطَي 0105 أ/ب). "
        "**ما زال بلا قياسِ تشغيلِ محوٍ حقيقيٍّ على الإنتاج.**",
    ),
    (
        "MAE-11",
        "**طلباتُ هجرات الخارطة التي لم تُذكر بعد (بلا لمس الحالة):** #800 #802 #808 #811 — فاللوحةُ لا تُنذر بها.",
    ),
]

# بنودٌ جديدة: (الرمز، المصدر، المسار، العنوان، الاعتماديّات، المعيار، الحالة، التقدّم، البداية، النهاية، أساسُ التاريخ، الجهد، البوّابة، طلب الدمج، المرجع، الملاحظة، الترتيب)
NEW_ITEMS = [
    (
        "N-080",
        "N",
        "ops",
        "حرّاسُ CI: البياناتُ الشخصيّة في md/docs، وتصادمُ الترقيم، وحجمُ الدستور",
        "",
        "حارسُ البيانات الشخصيّة يمسح md/docs (تحذيرٌ حتى 2026-10-10 ثمّ فشل)، وscripts/check_numbering.py يكشف تصادمَ الترقيم، وسقّاطةٌ لحجم CLAUDE.md (tests/test_claude_md_size.py)؛ تحذيرٌ لا تنبيهٌ عند تعذّر الجلب وتنبيهٌ عند بلوغ سقف الطلبات.",
        "done",
        100,
        D(2026, 10, 3),
        DAY,
        "W-20261003-005، نُشر main@2f36ff0 (2026-10-03، تأكيدٌ مباشرٌ من جلسة النشر)",
        1.0,
        "",
        "#807",
        "",
        "**بندٌ جديدٌ بقاعدة الإدراج (لا بندَ قائمٌ يغطّيه).** ملاحظاتُ 0105 أُدخلت (تحذيرٌ عند تعذّر الجلب، تنبيهٌ عند سقف الطلبات، توثيقُ حدّ السياق). اختباراتٌ جديدة: test_numbering_guard وtest_personal_data_guard وtest_claude_md_size. "
        "**حارسُ الترقيم (قرأتُ سكربتَه) يفحص بادئاتِ ADR ورموزَ القيود في constraint_registry فقط — لا ترقيمَ هجرات الخارطة.**",
        808,
    ),
    (
        "N-081",
        "N",
        "frontend",
        "سجلُّ الكادر: تخطيطُ الجدول (الاسمُ سطرٌ واحد، تسعةُ أعمدة، بطاقاتٌ على الجوال)",
        "N-078",
        "اسمُ المنتسب سطرٌ واحد بنقاطٍ مع title؛ تسعةُ أعمدة (عشرةٌ للمغادرين) بأصنافٍ c-* مجموعُ نسبها مئة؛ على الجوال ≤640px بطاقةٌ لكلّ منتسب بلا تمريرٍ أفقيّ؛ حارسُ tests/test_staff_register_columns.py وقياسُ الأسماء في e2e.",
        "doing",
        90,
        D(2026, 10, 2),
        None,
        "W-20261002-044، دُمج main@e5fe48c3 (2026-10-03) ولم يُنشر",
        2.0,
        "",
        "#809",
        "",
        "**بندٌ جديدٌ بقاعدة الإدراج.** **قياسُ جلسة التنفيذ على 1366×768 قبل الإصلاح:** التفّ الاسمُ في 39 صفّاً من 50، وعُصر عمودُ «الدخول» إلى 13px في «المغادرون»، وعلى الجوال جدولٌ 1024px في 343px. "
        "12 ← 9 أعمدة بدمج الرقمَين وجوّال/بريد وسكن/جنسيّة في خلايا بسطرين. تلميحاتُ أنواعٍ في core/templatetags/sorting.py؛ **تسجيلُ سقّاطة mypy (--update) في إيداعٍ لاحق** بنصّ الطلب. "
        "**لم يُنشر بعدُ ولا قياسَ بعد النشر** — يُغلق done بنشرٍ مؤكَّد.",
        809,
    ),
]

# (الرمز، (القيمة الحاليّة، تاريخ القياس) المتوقَّعان، القيمة الجديدة، تاريخُ القياس الفعليّ، مرجعُ القياس يُلحق بمصدر المؤشّر)
KPI_UPDATES = [
    (
        "V-K01",
        (273111.0, D(2026, 10, 3)),
        273230.0,
        D(2026, 10, 3),
        "0702، tests.css_source.shipped_size() في حاوية بلا شبكة على main@2eb36411، 2026-10-03: 273,230 من سقف 275,456، الهامش 2,226 بايتاً",
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
        ("roadmap", "0052_sync_items_2026_10_03c"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
