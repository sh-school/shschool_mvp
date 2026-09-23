"""مزامنةُ الخارطة مع ما دُمج بين مزامنة 0002 (#467) ويوم 2026-09-22.

حارسةٌ كـ0002: لا تلمس بنداً إلّا إن كانت حالتُه وتقدّمُه ما كانا في آخر لقطة (`expect`)،
فما عدّله المطوّرُ من الصفحة بعدها يبقى. تُلحِق سطراً مؤرَّخاً بالملاحظة ولا تحذف منها.
والبنودُ الجديدة (`N-…`) تُنشأ إن غابت وحدها — فلا تُكرَّر ولا يُكتب فوق ما أُنشئ يدوياً.

لا تحسم D-12 ولا تُغلق U-30: طلباتُ D-12 الثلاثة (#450، #451، #452) دُمجت صباحَ 09-21
وأبقت مزامنةُ 0002 مساءً القرارَ «بانتظار المالك» — فالحسمُ للمالك لا لهجرة.
"""

import datetime

from django.db import migrations

STAMP = "[2026-09-22]"
DAY = datetime.date(2026, 9, 22)

# (الرمز، (الحالة، التقدّم) المتوقَّعان، الحالة الجديدة، التقدّم الجديد، طلب الدمج، سطر الملاحظة)
UPDATES = [
    ("N-002", ("doing", 90), "done", 100, "#473", "أُغلق: #473 مدموج."),
    (
        "N-003",
        ("doing", 90),
        "done",
        100,
        "#472 #474",
        "أُغلق: #472 (تواصل المطوّر) و#474 (سجلّ الصلاحيّات) مدموجان.",
    ),
    (
        "H-02",
        ("doing", 60),
        "done",
        100,
        "#423 #450",
        "أُغلق: #450 مدموج — لا `border-radius: 6px` حرفيّاً في CSS بعد اليوم (`--radius-1-5`).",
    ),
    (
        "DBT-19",
        ("todo", 0),
        "done",
        100,
        "#468",
        "أُغلق: #468 أضاف حارسَ حجم الملفّات إلى docs/governance/regression_guards.md.",
    ),
    (
        "DBT-20",
        ("todo", 0),
        "done",
        100,
        "#468",
        "أُغلق: #468 ثبّت العتبة 1000 والهامش 25 سطراً ووثّق الهامشَ استثناءً مقصوداً من «النقص يسقط».",
    ),
    (
        "DBT-09",
        ("todo", 0),
        "done",
        100,
        "",
        "أُغلق بتحقّقٍ بلا تعديل: main@d126733d بلا علامة TODO/FIXME حقيقيّة خارج الهجرات"
        " والاختبارات (الباقي قيمُ تعدادٍ `ItemStatus.TODO` ونصُّ حارس placeholder)؛"
        " زالت الثلاثُ ضمن طلباتٍ أخرى.",
    ),
    (
        "U-02",
        ("doing", 50),
        "doing",
        50,
        "",
        "#408 مدموج (لا مفتوح). الباقي wave3-f وحدها حتى إغلاق U-23.",
    ),
]

# عملٌ دُمج بلا بندٍ في الخارطة: (الرمز، المسار، العنوان، طلب الدمج)
NEW_ITEMS = [
    ("N-004", "frontend", "الإدارة: بطاقاتُ مراقبة المطوّر وتخطيطٌ بلا تمريرٍ رأسيّ", "#465"),
    ("N-005", "frontend", "دليلُ الهويّة والأيقونات: أمثلةُ الشيفرة مطويّةٌ افتراضيّاً", "#469"),
    ("N-006", "frontend", "الإدارة: 25 صفّاً في القوائم وتحسيناتُ الاستعمال والجوّال", "#470"),
    (
        "N-007",
        "frontend",
        "«لا عضويّة نشطة» بصفحة الخطأ الموحّدة وزرّ خروج، وذيلُ المنصّة في بطاقة الدخول",
        "#471",
    ),
    (
        "N-008",
        "frontend",
        "الإدارة: بحثٌ سريعٌ في القائمة العلويّة وتعريبُ AXES وTOKEN BLACKLIST",
        "#475",
    ),
    ("N-009", "backend", "الزيارة الصفّيّة: تاريخٌ افتراضيٌّ يومَ دراسة، ورسالةٌ صريحة للعطلة", "#476"),
    (
        "N-010",
        "sec",
        "صلاحيّات /admin/ الفعليّة: المديرُ is_staff مقيّد، وفنّيّ تقنية المعلومات بنافذته",
        "#477",
    ),
    ("N-011", "frontend", "صفحةُ قفل axes بهويّة المنصّة بدل النصّ الخام، متجاوبةٌ على الأجهزة", "#478"),
    (
        "N-012",
        "mobile",
        "خارطةُ التجويد: اسمٌ صريحٌ لمرشّحات الخريطة الزمنيّة على الجوّال (axe select-name)",
        "#481",
    ),
]

NEW_ITEMS_FIRST_ORDER = 429  # بعد N-003 (428)


def sync(item_model):
    """تُطبِّق التحديثاتِ الحارسة؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, expected, status, progress, pr, line in UPDATES:
        item = item_model.objects.filter(code=code).first()
        # الملاحظةُ الموجودة تمنع التكرار حين لا تتغيّر الحالة (U-02).
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
    for offset, (code, lane, title, pr) in enumerate(NEW_ITEMS):
        if item_model.objects.filter(code=code).exists():
            continue
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
            note=f"{STAMP} عملٌ دُمج بلا بندٍ في الخارطة، سُجّل مُغلقاً برقم طلبه.",
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
        ("roadmap", "0002_sync_items_with_merged_work"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
