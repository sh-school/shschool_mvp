"""مزامنةُ الخارطة التاسعة (2026-09-25): ما اندمج ونُشر بعد #577 و#571 — #572 وM-05 (#579) وDBT-55 (#581).

حارسةٌ كسابقاتها: لا تلمس بنداً إلّا إن كانت حالتُه وتقدّمُه ما في آخر لقطة؛ والملاحظةُ الموجودة لا تُلحَق ثانيةً؛ ورمزُ الطلب يُضاف إلى
الحقل لا يستبدله؛ ولا يُملأ مؤشّرٌ إلّا إن لم يُقَس قطّ. كلُّ رقمٍ فيها من نصّ الطلب المدموج أو من إخطار جلسة النشر أو من صاحب الطلب
(وقد نُسب إلى صاحبه).

- **DBT-53 → منجز** بـ#572: operations/models.py (2243 سطراً) حزمةٌ بوحداتٍ حسب المسؤوليّة، منشورٌ على الإنتاج.
- **DBT-55 → منجز** بـ#581، و**تصحيحُ تقديره:** «+2px في ارتفاع رأس كلّ جدولٍ فرزٍ» لم يقع (قيسَ قبلُ وبعد: لا تغيّر)، فرُفعت بوّابةُ «المالك»
  التي وُسم بها خطأً. وأهدافُ سطح المكتب دون 24px: 49 ← 9 ← **2 (0.41%)** بخطّ أساس CI.
- **M-05 → منجز** بـ#579، والمؤشّرُ MK9 (مواضعُ 100vh بلا dvh) = 0 (كان 9 مواضع فعليّة والخطّة قدّرت 6–8).
- ملاحظةٌ على DBT-36 بهامش سقف CSS الخامّ (لا رقمَ مجموعاً للطلبين لأنّهما لم يُقاسا معاً).

لا يُدرج M-05b المقترَح من 8102 قبل تأكيد المالك، ولا REP-01 قبل قياسه الفعليّ من جلسة Git.
"""

import datetime

from django.db import migrations

STAMP = "[2026-09-25]"
DAY = datetime.date(2026, 9, 25)

# (الرمز، (الحالة، التقدّم) المتوقَّعان، الحالة الجديدة، التقدّم الجديد، رمزُ الطلب يُضاف، رفعُ البوّابة، سطر الملاحظة)
UPDATES = [
    (
        "DBT-53",
        ("todo", 0),
        "done",
        100,
        "#572",
        False,
        "أُغلق: #572 (8096) operations/models.py (2243 سطراً) صار حزمةً بوحداتٍ حسب المسؤوليّة — schedule وattendance وsubstitution "
        "وpermissions وcommon، وأكبرُها 857 سطراً — بلا تغييرٍ في مستوردٍ ولا هجرة (makemigrations --check = No changes detected)، "
        "وكلُّ الأسماء مُعاد تصديرُها. حارسان: tests/test_relative_imports_resolve.py (استيرادٌ نسبيٌّ محلّيٌّ انكسر بالتقسيم في "
        "المحاولة الأولى فصار له حارس) وسقّاطةُ حجم الملفّات. **منشورٌ على الإنتاج (main@38181bc، دورةٌ منفردة، نحو 06:50 الدوحة "
        "2026-09-25).** فحصُ ما بعد النشر (جلسة النشر و8096): استيرادُ operations.models يُخرج 25 نموذجاً كلَّها في الحزمة (لا ناقص) "
        "ومعها _uuid و_excuse_upload_path اللتان تشير إليهما الهجرات؛ مهامّ Celery 28 وتُستورد كلُّها؛ Session يُقرأ (4140 صفّاً)؛ لا "
        "ModuleNotFoundError ولا Traceback في الخدمات الثلاث؛ الدخول 200 و/health/ سليم.",
    ),
    (
        "DBT-55",
        ("todo", 0),
        "done",
        100,
        "#581",
        True,
        "أُغلق: #581 (8103، main@5c50a46c، 03:37Z) min-block-size: 24px في التعريف المركزيّ .th-sort (31-modules-2.css) وحُذفت النسخةُ "
        "المكرَّرة من كتلة الهاتف (50-utilities)؛ لا قالبَ ولا صفحةَ خاصّة — بطلب المالك «بشكلٍ مركزيّ في ملفّات CSS» بحسب 8103. حارسٌ "
        "test_column_sort_headers_reach_the_mouse_minimum_in_the_central_rule (طفرةٌ أسقطته). **تصحيحٌ لتقدير هذا البند:** «+2px في "
        "ارتفاع رأس كلّ جدولٍ فرزٍ» **لم يقع** — قِيس على 25 صفحةً قبلُ وبعدُ (1440، فأرة): ارتفاعُ ترويسة الجدول 64.8px في الحالتين "
        "وارتفاعُ أيّ صفحةٍ لم يتغيّر، والصفُّ يحدّده أطولُ رأسٍ وهو الملتفُّ على سطرين (44.8px) لا المفرد (22.4 ← 24)، وصفحةٌ واحدةٌ "
        "فقط من الخمس والعشرين فيها رؤوسُ فرز (سجلّ الموظفين) لا كلُّ جدول؛ فكان تقديرُ «كلِّ جدول» مبالغاً، وكانت بوّابةُ «المالك» "
        "عليه خطأً فرُفعت (قرّر المالكُ ونُفّذ). **الأرقامُ الرسميّة من CI (خطّ الأساس، chromium/desktop، 491 هدفاً):** الأهدافُ دون 24px "
        "من 49 (10.0%) قبل DBT-44 إلى 9 بعده إلى **2 (0.41%)**؛ والباقي: هدفٌ في staff_list (كان 8 ← 1؛ عنصرُه غيرُ محسوم والأرجحُ رأسُ "
        "فرزٍ يلتفّ في متصفّح CI) وخانةُ clinic-check (DBT-45). والجوّالُ (375px، لمس) بلا تغيير: صفرٌ دون 24px. **منشورٌ على "
        "الإنتاج (main@38181bc).**",
    ),
    (
        "M-05",
        ("todo", 0),
        "done",
        100,
        "#579",
        False,
        "أُغلق: #579 (8102، main@1d7782d3، 03:20Z) كلُّ 100vh يتبعه 100dvh. الحارسُ tests/test_dynamic_viewport.py (يعدّ 100vh بلا "
        "100dvh بعده في القاعدة نفسها، ويستثني tailwind.min.css المستورَد والتعليقات) = 0 على main بعد الدمج؛ كان **9 مواضع فعليّة** "
        "(الخطّةُ قدّرت 6–8): لوحةُ الهامبرغر .nb-bar والقائمةُ الفرعيّة .sd-drawer وصفحةُ الدخول وpage-noscroll (فوق 1024) وثلاثةُ "
        "قوالب (الأخطاء وعدم الاتّصال ×2). معماريّاً: mobMenuTop في base.js صار يضبط --nb-top فقط وCSS يحسب "
        "calc(100dvh - var(--nb-top,54px)) — لا معادلةَ ارتفاعٍ في JS، والحارسُ يمنع vh في السكربتات؛ والفاحصُ نفسُه أُثبت فشلُه على ست "
        "صيغٍ خاطئة وعلى تعديلٍ مقصودٍ في المصدر. **قياسٌ حيّ** عند 375×812 على عنصرٍ يأخذ قواعد .nb-bar الحقيقيّة: --nb-top:97px ← "
        "max-height 715px (= 812−97) والافتراضيُّ 758px، وصفحةُ الدخول بلا تمريرٍ زائد؛ وصافي CSS الخامّ +218 بايتاً. **لم يُتحقَّق منه:** "
        "مسارُ الهامبرغر كاملاً بجلسةٍ مسجَّلة الدخول، وسلوكُ dvh الحيّ أثناء طيّ شريط المتصفّح على جهازٍ حقيقيّ (يبقى على قائمة §8)، "
        "وtest_mobile_audit (Chromium) حكم عليه CI. **منشورٌ على الإنتاج (main@38181bc):** CSS المبصومُ يُخدَم 200 و100dvh حاضر.",
    ),
    (
        "DBT-36",
        ("todo", 0),
        "todo",
        0,
        "",
        False,
        "بعد #581: CSS الخامّ 468.94KB من سقف 470KB (+0.09KB عن main بحسب 8103)، الهامشُ ≈ 1.06KB؛ و#579 أضاف +218 بايتاً (8102) — "
        "ولم يُقَس المجموعُ بعد الطلبين معاً.",
    ),
]

# (الرمز، القيمةُ الأولى، الوحدة، مرجعُ القياس) — يُملأ مؤشّرٌ نصّيّ الأساس لم يُقَس قطّ
FIRST_READINGS = [
    (
        "MK9",
        0.0,
        "",
        "بعد #579: tests/test_dynamic_viewport.py = 0 على main (كان 9 مواضع فعليّة)",
    ),
]


def _add_pr(existing, pr):
    """تُضيف رموزَ الطلبات الجديدة إلى ما في الحقل بلا تكرار."""
    return " ".join(dict.fromkeys([*existing.split(), *pr.split()]))


def sync(item_model):
    """تُطبِّق تحديثاتِ البنود الحارسة؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, expected, status, progress, pr, clear_gate, line in UPDATES:
        item = item_model.objects.filter(code=code).first()
        if item is None or (item.status, item.progress) != expected or line in item.note:
            continue
        item.status, item.progress = status, progress
        if pr:
            item.pr = _add_pr(item.pr, pr)
        if clear_gate:
            item.gate = ""
        item.note = f"{item.note}\n{STAMP} {line}".strip()
        item.save(update_fields=["status", "progress", "pr", "gate", "note", "updated_at"])
        changed.append(code)
    return changed


def _record(kpi, value):
    """تكتب قياسَ اليوم في السجلّ: تستبدل نقطةَ اليوم إن وُجدت، وإلّا تُلحقها."""
    today = DAY.isoformat()
    history = [point for point in (kpi.history or []) if point.get("d") != today]
    history.append({"d": today, "v": value})
    kpi.current, kpi.measured_at, kpi.history = value, DAY, history


def first_readings(kpi_model):
    """تملأ القيمةَ الحاليّةَ لمؤشّرٍ نصّيّ الأساس إن لم يُقَس قطّ (بحدّ حقل المصدر 255)؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, value, unit, source_note in FIRST_READINGS:
        kpi = kpi_model.objects.filter(
            code=code, current__isnull=True, measured_at__isnull=True
        ).first()
        if kpi is None:
            continue
        source = (
            kpi.source if source_note in kpi.source else f"{kpi.source} ({source_note})".strip()
        )
        if len(source) > 255:
            source = kpi.source
        _record(kpi, value)
        if unit and not kpi.unit:
            kpi.unit = unit
        kpi.source = source
        kpi.save(
            update_fields=["current", "measured_at", "history", "unit", "source", "updated_at"]
        )
        changed.append(code)
    return changed


def forwards(apps, schema_editor):
    item_model = apps.get_model("roadmap", "RoadmapItem")
    # قاعدةٌ بلا استيراد (اختبار، شجرةٌ جديدة): لا شيء يُزامَن، ولا بنودٌ يتيمة.
    if not item_model.objects.exists():
        return
    sync(item_model)
    first_readings(apps.get_model("roadmap", "RoadmapKpi"))


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0020_git_repo_remediation_plan"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
