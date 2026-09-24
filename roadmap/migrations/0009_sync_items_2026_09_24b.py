"""مزامنةُ الخارطة الثانية يومَ 2026-09-24، بعد نشر main@cf4b04d.

حارسةٌ كـ0008: لا تلمس بنداً إلّا إن كانت حالتُه وتقدّمُه ما في آخر لقطة؛ والملاحظةُ الموجودة لا تُلحَق
ثانيةً؛ والبندُ الجديد يُنشأ إن غاب.

- **LAY-01 وLAY-02** يُغلقان بـ#517: مرجعُ LAY-01 (`docs/design/page_layouts.md`) اندمج فيه، وبه أتمّت جلسةُ
  الهويّة المواصفاتِ وصفحةَ الدليل (كانت 60 «بقي الدمج»).
- **H-03 لا يُغلق:** رُفعت 44 تصريحاً، وبقيت 23 في الشبكات الكثيفة تنتظر مراجعةَ المالك البصريّة.
- **إصلاحُ التشغيل الليليّ (N-026)** مُغلقٌ برقم طلبه، وأوّلُ ليلةٍ بعده هي تحقّقُه الفعليّ (القضيّة #422).
"""

import datetime

from django.db import migrations

STAMP = "[2026-09-24]"
DAY = datetime.date(2026, 9, 24)

# (الرمز، (الحالة، التقدّم) المتوقَّعان، الحالة الجديدة، التقدّم الجديد، طلب الدمج، سطر الملاحظة)
UPDATES = [
    (
        "LAY-01",
        ("todo", 0),
        "done",
        100,
        "#517",
        "أُغلق: حسم المالكُ D-16 (2026-09-23)، والمواصفاتُ مقبولةٌ في docs/design/page_layouts.md (#517).",
    ),
    (
        "LAY-02",
        ("doing", 60),
        "done",
        100,
        "#517",
        "أُغلق: #517 مواصفاتُ الأنماط السبعة وصفحةُ الدليل /styleguide/layouts/، وأنماطُ الدليل في ملفٍّ لا يُشحن "
        "لغير المطوّر.",
    ),
    (
        "H-03",
        ("doing", 30),
        "doing",
        70,
        "#451 #520",
        "#520: 44 تصريحاً دون 12px صارت var(--text-xs)، وK3 = 0 في الوضعين على الرحلات الخمس، وحارسُ "
        "tests/test_font_scale.py. بقيت 23 في الشبكات الكثيفة (رصدُ الحصّة، التفريغات، خليّةُ المعلّم، الدونات…) "
        "تنتظر مراجعةَ المالك البصريّة قبل رفعها.",
    ),
    (
        "M-11",
        ("todo", 0),
        "done",
        100,
        "#509 #523",
        "أُغلق: رسائلُ الخطأ تبقى حتّى الإغلاق أو ≥12ث، والتوستُ فوق الشريط السفليّ (#509، #523)؛ "
        "الحارس tests/test_toast_stays_readable.py، وK16 = نعم. (أبلغت به جلسةُ «اصلاحات 02».)",
    ),
]

# بنودٌ جديدةٌ لعملٍ دُمج بلا بند: (الرمز، المسار، العنوان، طلب الدمج، ملاحظةٌ إضافيّة)
NEW_ITEMS = [
    (
        "N-026",
        "quality",
        "التشغيلُ الليليّ: اختبارا متصفّحٍ خارجَ الخطوة الرئيسيّة، وحارسٌ يمنع تكرارها",
        "#522",
        "سقطت الليالي 09-20..09-23 (القضيّة #422) لأنّ ملفّين يطلبان pytest_playwright شُغِّلا في الخطوة المتسلسلة. "
        "التحقّقُ الفعليّ في أوّل ليلةٍ بعد الدمج.",
    ),
    (
        "N-027",
        "frontend",
        "الورقةُ المستقلّة: التصديرُ بإشعارٍ عائمٍ من صفحة الجدول لا بصفحة متابعة",
        "#521",
        "",
    ),
    (
        "N-028",
        "backend",
        "الإشغالُ عن المعلّم الغائب: إبلاغُ البديل وظهورُ الحصّة عنده، والمنسّقُ من قسمه",
        "#515",
        "",
    ),
]

NEW_ITEMS_FIRST_ORDER = 458  # بعد N-025 (457)


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


def add_missing(item_model):
    """تُنشئ بنودَ العمل المدموج الغائبة؛ تُرجع رموزَ ما أُنشئ."""
    created = []
    for offset, (code, lane, title, pr, extra) in enumerate(NEW_ITEMS):
        if item_model.objects.filter(code=code).exists():
            continue
        note = f"{STAMP} عملٌ دُمج بلا بندٍ في الخارطة، سُجّل مُغلقاً برقم طلبه."
        item_model.objects.create(
            code=code,
            src="NEW",
            lane=lane,
            title=title,
            status="done",
            progress=100,
            start_date=DAY,
            end_date=DAY,
            date_basis="محدَّث يدوياً",
            pr=pr,
            note=f"{note} {extra}".strip(),
            sort_order=NEW_ITEMS_FIRST_ORDER + offset,
        )
        created.append(code)
    return created


def forwards(apps, schema_editor):
    item_model = apps.get_model("roadmap", "RoadmapItem")
    # قاعدةٌ بلا استيراد (اختبار، شجرةٌ جديدة): لا شيء يُزامَن، ولا بنودٌ يتيمة.
    if not item_model.objects.exists():
        return
    sync(item_model)
    add_missing(item_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0008_sync_items_2026_09_24"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
