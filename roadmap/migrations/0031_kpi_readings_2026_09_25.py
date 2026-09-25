"""قراءاتُ المؤشّرات (2026-09-25): ما قاسه مالكو المسارات بمصدره وتاريخه، وخمسةُ مؤشّراتِ مسار الديون، ومؤشّرُ توافر الإنتاج، وإعادةُ تعريف PK18 وV-K38.

**قياساتٌ مقترحةٌ من مالكي المسارات** (8201 و8202 و8203 و8204 و8205 و8206 و8207 و8208 و8101) بأدوات المستودع وقراءات لوحاتٍ بإذن المالك؛ كلٌّ في
سطر المصدر بتاريخه. المرايا (مؤشّراتٌ تكرّر قياسَ غيرها) تُكتب بالقيمة نفسها ومصدرِ الأصل. **القياسُ المحلّيّ ليس إنتاجاً** حيث ذُكر ذلك.

حارسةٌ كسابقاتها: لا يُمسّ مؤشّرٌ إلّا إن كانت (قيمتُه الحاليّة وتاريخُ قياسه) ما في آخر لقطة، ولا يُعاد لحقُ مرجعٍ مرّتين، وسطرُ المصدر لا يتجاوز
255 حرفاً (وإلّا تبقى القيمةُ محدَّثةً والمصدرُ كما هو)، ويُنشأ الغائبُ وحدَه. والمستودعُ عامّ: أعدادٌ ومصادرُ محايدة بلا أسماء ولا بيانات شخصيّة.

- **مؤكَّدٌ من المالك مباشرةً:** تسجيلُ DK1..DK5 (مسار الديون)، ومؤشّرُ توافر الإنتاج، وتعريفُ PK18 (أربعُ وثائقَ حيّةٍ بتاريخ مراجعةٍ خلال 90 يوماً)،
  وتعريفُ V-K38 على المرئيّ فقط بلا تعليقات الشيفرة.
- **لا يُسجَّل هنا:** ما لم يُقَس (MK12 وMK20 وMK22 وMK23 وMK26..29)، وقراءاتُ Lighthouse المخبريّة (MK13 وMK25)، وتعريفُ PK7 وUK9 وV-K35 (بلا اتّفاق)،
  ومؤشّرٌ مقترَح «بلا تمريرٍ وبلا فراغٍ يفوق ثلثَ النافذة» (لم يُعتمد).
"""

import datetime

from django.db import migrations

STAMP = "[2026-09-25]"
DAY = datetime.date(2026, 9, 25)
D = datetime.date
SEP = D(2026, 9, 21)

# (الرمز، (القيمة الحاليّة، تاريخ القياس) المتوقَّعان، القيمة الجديدة، مرجعُ القياس يُلحق بمصدر المؤشّر)
KPI_UPDATES = [
    # ── الواجهة والهويّة (8205 على main@ff70a32f، و8101 على main@5877f356) ──
    (
        "V-K01",
        (248203.0, SEP),
        259134.0,
        "8101 على main@5877f356 09-25: 259,134؛ وقاس 8205 261,568 على ff70a32f",
    ),
    ("PK10", (242.4, SEP), 253.1, "مرآة V-K01: 259,134 بايتاً = 253.1KB (main@5877f356، 09-25)"),
    (
        "MK14",
        (None, None),
        259134.0,
        "مرآة V-K01: 259,134 بايتاً = 97.3% من سقف الحارس (8101، main@5877f356، 09-25)",
    ),
    (
        "V-K36",
        (97.8, None),
        95.1,
        "بديلٌ ساكن (8101، main@5877f356): custom 445,115 + tailwind 13,041 من 481,791 ← هامش 23,635 بايتاً؛ والحارسُ يقيس الأوراقَ على الصفحات الأربع",
    ),
    ("V-K02", (14.0, SEP), 17.0, "8205، main@ff70a32f، 09-25: ارتفع بـ#559 ولا سقّاطةَ تحرسه"),
    ("V-K04", (95.0, SEP), 89.0, "8205، main@ff70a32f، 09-25"),
    ("V-K05", (90.7, SEP), 91.4, "8205، main@ff70a32f، 09-25"),
    ("V-K06", (60.0, SEP), 31.0, "8205، main@ff70a32f، 09-25 (#450)"),
    ("V-K10", (14.0, SEP), 13.0, "8205، main@ff70a32f، 09-25"),
    (
        "V-K16",
        (250.0, SEP),
        261.0,
        "8205، main@ff70a32f، 09-25: النموُّ في قوالب المنتج لا الدليل",
    ),
    ("V-K19", (4.0, SEP), 0.0, "8205/8104 بعد #583 و#599، 09-25"),
    (
        "V-K20",
        (34.0, SEP),
        124.0,
        "8205/8204، الأداة الرسميّة، 09-25: منها 88 في templates/styleguide (مطوّرٌ فقط) وخارجَه 36",
    ),
    ("LK5", (990.0, D(2026, 9, 24)), 996.0, "8205، main@ff70a32f، 09-25"),
    ("PK9", (2.0, SEP), 1.0, "8101/8205، 09-25: عقدةٌ واحدة (notification_inbox) منذ #469"),
    ("V-A1", (2.0, SEP), 1.0, "8101/8205، 09-25: عقدةٌ واحدة (notification_inbox) منذ #469"),
    ("V-C1", (58.1, SEP), 56.84, "8205/8208، main@ff70a32f، 09-25: 266,194 من 468,305 بايتاً"),
    ("PK11", (58.1, SEP), 56.84, "مرآة V-C1 (8205/8208، main@ff70a32f، 09-25)"),
    # ── الجوال (8206، سقّاطةُ mobile_audit وأدواتُها على main@ff70a32f) ──
    ("PK8", (58.0, SEP), 0.0, "مرآة MK1 (8206، 09-25): Chromium 0 من 431 وWebKit 0 من 434"),
    ("MK3", (None, None), 0.0, "8206، 09-25: 0 من 25 صفحةً جوالاً وسطحَ مكتب (أدنى خطٍّ 12px)"),
    ("MK4", (None, None), 0.0, "8206، 09-25: صفرُ صفحةٍ بتجاوزٍ أفقيّ (mobile_audit)"),
    ("MK5", (None, None), 0.0, "8206، 09-25: صفرُ صفحة (mobile_audit)"),
    ("MK6", (None, None), 0.0, "8206، 09-25: لا — الشريطُ السفليّ مخفيٌّ ≥641px؛ يحجبه MD2"),
    ("MK10", (None, None), 1.0, "8206، 09-25: نعم (#602 وحارسُ لمس لوحة الأوامر)"),
    ("MK11", (None, None), 0.0, "8206، 09-25: 9 حقول رقميّة كلُّها بـinputmode"),
    ("MK15", (None, None), 0.0, "8206، 09-25: 0 من 3 جداولَ ثقيلةٍ ببطاقات"),
    ("MK16", (None, None), 1.0, "8206، 09-25: نعم (حارسُ بقاء رسائل الخطأ)"),
    (
        "MK17",
        (None, None),
        23.0,
        "8206، 09-25: من 41، + 3 زخرفيّة مستثناة، والباقي في الشبكات الكثيفة",
    ),
    ("MK19", (None, None), 1.0, "8206، 09-25: من 3"),
    (
        "MK21",
        (None, None),
        1.0,
        "8206، 09-25: نعم لسقّاطة الجوال؛ وaxe وWeb Vitals على Chromium وحده",
    ),
    ("MK24", (None, None), 0.0, "8206، 09-25: من 80 (لا يشمل قوالبَ الطباعة/PDF/البريد)"),
    # ── سطح المكتب (8207: Chromium على خادم جلسةٍ محلّيّ لـmain@ff70a32 — بياناتٌ محلّيّة لا إنتاج) ──
    (
        "PK14",
        (None, SEP),
        66.0,
        "=D1 — 8207، 09-25، Chromium على خادم جلسةٍ محلّيّ لـmain@ff70a32: 1366×768 (16 من 47 لوحة بلا تمرير)؛ 59.6% على 1366×625 و89.4% على 1920×1080؛ محلّيّ لا إنتاج",
    ),
    (
        "V-D1",
        (None, None),
        66.0,
        "=D1 (مرآة PK14) — 8207، 09-25، Chromium على خادم جلسةٍ محلّيّ لـmain@ff70a32: 1366×768، 47 لوحةً؛ محلّيّ لا إنتاج",
    ),
    (
        "V-D2",
        (None, None),
        0.0,
        "=D2 — 8207، 09-25، Chromium على خادم جلسةٍ محلّيّ لـmain@ff70a32: لا فيضانَ أفقيّاً في 531 خليّة؛ محلّيّ لا إنتاج",
    ),
    # ── التشغيل (8203، 8097) ──
    (
        "PK15",
        (0.9, SEP),
        1.02,
        "8203، 09-25: وسيط فتح←دمج 1.02 ساعة (n=403 خلال 14 يوماً؛ p90=6.6)",
    ),
    ("PK16", (0.0, SEP), 0.0, "8203، 09-25: لا فشلَ في آخر 20 نشراً (63 نشراً 09-19..09-25)"),
    (
        "RK1",
        (287.0, DAY),
        304.0,
        "8097، 09-25، بتعريف RD5 المعدَّل: يستثني الحيَّ والمفتوحَ بطلب",
    ),
    (
        "RK5",
        (None, None),
        0.0,
        "8097، main@5877f356 بعد #604، 09-25: لا مطابقةَ حقيقيّةً في أيّ ملفٍّ متتبَّع بما فيها tests/",
    ),
    (
        "RK7",
        (6.0, DAY),
        1.0,
        "8203، 09-25، بالتعريف المؤكَّد: بلا وسم نشر-عاجل (#490 وحدَه؛ الخمسةُ الباقية موسومة)",
    ),
    # ── Backend (8202) والجودة (8204) والأمن (8201) ──
    ("PK5", (215.0, SEP), 207.0, "8202/8101، layering_ratchet على main@ff70a32، 09-25"),
    (
        "UK8",
        (None, None),
        12.0,
        "8202، 09-25: 12 تطبيقاً/34 جملة (بلا تغيّر عن 09-19)؛ استثناءاتٌ موثَّقة 7",
    ),
    ("UK12", (None, None), 632.0, "8202، wc -l، 09-25"),
    (
        "PK6",
        (1821.0, SEP),
        1735.0,
        "8204، mypy_ratchet_baseline.json، 09-25: 160 ملفّاً بـmypy 1.10.0",
    ),
    ("UK10", (None, None), 1735.0, "مرآة PK6 (8204، 09-25)"),
    (
        "UK11",
        (None, None),
        3.0,
        "8204، 09-25: TARGETS = core وshschool وgovernance (3 من 21؛ 23 تطبيقاً بعدّ 8208)",
    ),
    ("UK6", (None, None), 2.0, "8201، 09-25: بحثٌ نصّيٌّ في تعريف نموذج المستخدم على main@ff70a32f"),
]

# مؤشّراتٌ جديدة (يُنشأ الغائبُ وحدَه):
# (الرمز، المسار، الاسم، الأساس، الحاليّ، الهدف، الأساس نصّاً، الهدف نصّاً، الاتّجاه، الوحدة، المصدر، الجهةُ، الترتيب)
NEW_KPIS = [
    (
        "DK1",
        "debt",
        "ملفّاتُ .py فوق 1000 سطر (سقّاطةُ الحجم)",
        13.0,
        11.0,
        0.0,
        "13 (2026-09-21، مسجَّلٌ في أساس السقّاطة لا مقيس)",
        "0 بلا استثناءٍ موثَّق بحلول 12-17",
        "down",
        "count",
        "tests/file_size_ratchet.py (measure()) على main@ff70a32f، 2026-09-25 — 8208",
        443,
    ),
    (
        "DK2",
        "debt",
        "أسطرُ الفائض فوق 1000 في تلك الملفّات",
        7082.0,
        5728.0,
        0.0,
        "7,082 (مصدرُ أساس DK1 نفسُه)",
        "0",
        "down",
        "سطر",
        "الأداةُ نفسُها: مجموعُ (الأسطر − 1000) على main@ff70a32f، 2026-09-25 — 8208",
        444,
    ),
    (
        "DK3",
        "debt",
        "دوالّ بتعقيدٍ حلقيّ 21–30 (درجة D)",
        38.0,
        38.0,
        None,
        "38 (القراءةُ الأولى)",
        "لا زيادة، ولا دالّةَ ≥ 28 (سقّاطةٌ غيرُ مبنيّة بعد)",
        "down",
        "count",
        "radon cc . --min D (radon==6.0.1) على main@ff70a32f، 2026-09-25 — 8208",
        445,
    ),
    (
        "DK4",
        "debt",
        "قمعُ المدقّقات في الشيفرة الحيّة (# noqa + type: ignore خارج tests والهجرات)",
        158.0,
        158.0,
        None,
        "158 (القراءةُ الأولى؛ 93 + 65)",
        "لا زيادة",
        "down",
        "count",
        "git grep على main@ff70a32f، 2026-09-25 — 8208",
        446,
    ),
    (
        "DK5",
        "debt",
        "قواعدُ ruff المعطَّلة عالميّاً",
        23.0,
        23.0,
        None,
        "23 (أربعٌ موسومةٌ مؤقّتاً/legacy)",
        "الأربعُ الموسومةُ ← 0",
        "down",
        "count",
        "pyproject.toml [tool.ruff.lint].ignore على main@ff70a32f، 2026-09-25 — 8208",
        447,
    ),
    (
        "OPK1",
        "ops",
        "توافرُ الإنتاج (Sentry Uptime، فحصٌ كلَّ دقيقةٍ من مسبّارات أوروبّا، 14 يوماً)",
        None,
        99.573,
        None,
        "",
        "لا هدفَ رقميّاً إلّا بقرار المالك",
        "up",
        "pct",
        "لوحة Sentry Uptime، 2026-09-25 14:35 الدوحة — قراءةُ 8203 بإذن المالك؛ نحو 86 دقيقةَ فحصٍ فاشلة أغلبُها متفرّقٌ (إعادةُ تشغيلٍ عند النشر) وأطولُها 09-17",
        448,
    ),
]

# إعادةُ تعريف مؤشّرٍ بقرار المالك: (الرمز، الاسمُ القديم بالضبط، الاسمُ الجديد، سببُ غياب القياس أو ""، الأساسُ نصّاً أو None، القيمةُ المسجَّلةُ اليومَ أو None، سطرُ المرجع يُلحق بالمصدر)
KPI_RESTATES = [
    (
        "PK18",
        "الوثائق الأربع للحوكمة الموقّعة",
        "الوثائقُ الأربع للحوكمة الحيّة (بتاريخ مراجعةٍ خلال 90 يوماً)",
        "",
        None,
        0.0,
        "تعريفٌ مؤكَّدٌ من المالك 09-25؛ القيمةُ الآن 0",
    ),
    (
        "V-K38",
        "صيغُ اسم المنتج وصيغُ «حفظ»",
        "صيغُ اسم المنتج المرئيّةُ (بلا تعليقات الشيفرة) وصيغُ «حفظ»",
        "لم يُقَس بعدُ بالتعريف الجديد: أمرٌ موثَّقٌ (git grep باستبعاد التعليقات) يُسجَّل قبلُ وبعدُ؛ وعدّ 8209 الأوّليّ نحو خمس صيغٍ مرئيّة في نحو 15 موضعاً",
        "نحو 5 صيغٍ مرئيّة (8209، 2026-09-25)",
        None,
        "تعريفٌ مؤكَّدٌ من المالك 09-25: المرئيُّ فقط؛ العدُّ السابق 12+ يشمل تعليقاتِ الشيفرة",
    ),
]

# ملاحظاتٌ على بنودٍ قائمة تُلحق مرّةً واحدة (الغائبُ يُترك)
ITEM_NOTES = [
    (
        "DBT-36",
        "تحديثٌ (8101، main@5877f356، 2026-09-25): بعد #607 و#609 هامشُ الخامّ **23,635 بايتاً** (custom 445,115 + tailwind 13,041 من 481,791)، "
        "والمصغَّرُ المشحون 259,134 (97.3% من سقف الحارس). لم تُغيَّر الحالةُ ولا الموعد، ولم يُحسم تعريفُ «بعد نزع التعليقات».",
    ),
    (
        "N-042",
        "تحديثٌ (جلسةُ الجدول وجلسةُ النشر، 2026-09-25): #621 مدموجٌ ومنشورٌ ضمن main@ead2606 (نحو 18:32 الدوحة) — حجبَ سكربتَي الجدول عن مسار for_pdf "
        "فزال **العَرَضُ** على تصدير الـPDF (تصييرُ القالب داخل حاوية العامل نجح قراءةً)؛ **والعلّةُ البنيويّة باقية**: لا staticfiles.json في العامل ولا الـbeat "
        "حتى يُنشر هذا البند. لم يُقَس بعدُ: تصديرُ PDF حقيقيٌّ من الواجهة على الإنتاج، وألّا تتجدّد المشكلةُ في Sentry (عند المالك/8203). لا بندَ مستقلّ لـ#621.",
    ),
]


def _record(kpi, value):
    """تكتب قياسَ اليوم في السجلّ: تستبدل نقطةَ اليوم إن وُجدت، وإلّا تُلحقها."""
    today = DAY.isoformat()
    history = [point for point in (kpi.history or []) if point.get("d") != today]
    history.append({"d": today, "v": value})
    kpi.current, kpi.measured_at, kpi.history = value, DAY, history


def _with_source(kpi, note):
    """تُلحق مرجعَ القياس بالمصدر دون تكرارٍ وبحدّ الحقل 255 (وإلّا يبقى المصدرُ كما هو)؛ والبادئةُ «=» تستبدل المصدرَ كلَّه (كان «لم يُقَس»)."""
    if not note:
        return kpi.source
    if note.startswith("="):
        replaced = note[1:].strip()
        return replaced if len(replaced) <= 255 else kpi.source
    if note in kpi.source:
        return kpi.source
    source = f"{kpi.source} ({note})".strip()
    return source if len(source) <= 255 else kpi.source


def sync_kpis(kpi_model):
    """تُحدِّث المؤشّراتِ التي لم تُمسّ منذ آخر لقطة (والأساسُ باقٍ)؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, expected, value, note in KPI_UPDATES:
        kpi = kpi_model.objects.filter(code=code).first()
        if kpi is None or (kpi.current, kpi.measured_at) != expected:
            continue
        source = _with_source(kpi, note)
        _record(kpi, value)
        kpi.source, kpi.why = source, ""
        kpi.save(update_fields=["current", "measured_at", "history", "source", "why", "updated_at"])
        changed.append(code)
    return changed


def add_kpis(kpi_model):
    """تُنشئ المؤشّراتِ الغائبةَ بقراءتها الأولى؛ لا تُعيد كتابةَ مؤشّرٍ موجود؛ تُرجع رموزَ ما أُنشئ."""
    created = []
    for (
        code,
        lane,
        name,
        baseline,
        current,
        target,
        baseline_text,
        target_text,
        direction,
        unit,
        source,
        order,
    ) in NEW_KPIS:
        if kpi_model.objects.filter(code=code).exists():
            continue
        kpi_model.objects.create(
            code=code,
            lane=lane,
            name=name,
            baseline=baseline,
            current=current,
            target=target,
            baseline_text=baseline_text,
            target_text=target_text,
            direction=direction,
            unit=unit,
            source=source[:255],
            measured_at=DAY,
            history=[{"d": DAY.isoformat(), "v": current}],
            extra={"track": "مسار الديون"} if lane == "debt" else {"track": "مسار التشغيل"},
            sort_order=order,
        )
        created.append(code)
    return created


def restate_kpis(kpi_model):
    """تُعيد تعريفَ مؤشّرٍ بقرار المالك ما دام اسمُه القديمُ كما هو؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, old_name, name, why, baseline_text, value, note in KPI_RESTATES:
        kpi = kpi_model.objects.filter(code=code, name=old_name).first()
        if kpi is None:
            continue
        kpi.name = name
        kpi.why = why
        if baseline_text:
            kpi.baseline_text = baseline_text
        kpi.source = _with_source(kpi, note)
        fields = ["name", "why", "source", "updated_at"]
        if baseline_text:
            fields.append("baseline_text")
        if value is not None:
            _record(kpi, value)
            fields += ["current", "measured_at", "history"]
        kpi.save(update_fields=fields)
        changed.append(code)
    return changed


def sync_item_notes(item_model):
    """تُلحق الملاحظاتِ بالبنود القائمة مرّةً واحدة؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, line in ITEM_NOTES:
        item = item_model.objects.filter(code=code).first()
        if item is None or line in item.note:
            continue
        item.note = f"{item.note}\n{STAMP} {line}".strip()
        item.save(update_fields=["note", "updated_at"])
        changed.append(code)
    return changed


def forwards(apps, schema_editor):
    item_model = apps.get_model("roadmap", "RoadmapItem")
    # قاعدةٌ بلا استيراد (اختبار، شجرةٌ جديدة): لا شيء يُزامَن، ولا مؤشّراتٌ يتيمة.
    if not item_model.objects.exists():
        return
    kpi_model = apps.get_model("roadmap", "RoadmapKpi")
    sync_kpis(kpi_model)
    add_kpis(kpi_model)
    restate_kpis(kpi_model)
    sync_item_notes(item_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0030_sync_items_2026_09_25i"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
