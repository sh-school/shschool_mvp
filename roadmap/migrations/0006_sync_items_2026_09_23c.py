"""مزامنةُ الخارطة الثالثة يومَ 2026-09-23: حزمةُ القياس والديونُ وعملٌ دُمج بلا بند.

حارسةٌ كـ0003–0005: لا تلمس بنداً إلّا إن كانت حالتُه وتقدّمُه ما في آخر لقطة، والملاحظةُ
الموجودة لا تُلحَق ثانيةً، والبندُ الجديد يُنشأ إن غاب.

DBT-13 وDBT-14 «محجوبان» لا مُغلقان: التحقّقُ منهما في لوحة Sentry وهي عند المالك وحدَه.
"""

import datetime

from django.db import migrations

STAMP = "[2026-09-23]"
DAY = datetime.date(2026, 9, 23)

# (الرمز، (الحالة، التقدّم) المتوقَّعان، الحالة الجديدة، التقدّم الجديد، طلب الدمج، سطر الملاحظة)
UPDATES = [
    (
        "M-00",
        ("todo", 0),
        "done",
        100,
        "#498",
        "أُغلق: #498 أداةُ قياسٍ حيّة (أهداف اللمس والنصّ والتجاوز) على رحلات خمسة أدوار، "
        "Chromium وWebKit وسطحَ مكتب، وسقّاطةٌ في axe-a11y. الأساس: K1 49.4%.",
    ),
    (
        "Q-03",
        ("todo", 0),
        "done",
        100,
        "#504",
        "أُغلق: #504 Lighthouse للجوال على خمس صفحاتٍ ليلاً (الوصوليّة لا تنزل، الأداء بسماح 15)؛ "
        "الأساس: الأداء 54–69 والوصوليّة 99. لم يعمل على مُشغِّل GitHub بعد — تشغيلُ 09-24 هو الاختبار.",
    ),
    (
        "Q-01",
        ("todo", 0),
        "doing",
        60,
        "#498",
        "الرحلاتُ الخمس مقيسةٌ في #498 (قيادة، مشرفُ جناح، معلّم، وليّ أمر، ممرّض). "
        "الباقي: وثيقةُ الرحلات المكتوبة.",
    ),
    (
        "Q-02",
        ("todo", 0),
        "doing",
        60,
        "#498",
        "WebKit يعمل في سقّاطة الجوال (#498). الباقي: توثيقُ فروق dvh والمنطقة الآمنة بين المحرّكين.",
    ),
    (
        "DBT-12",
        ("todo", 0),
        "done",
        100,
        "#497",
        "أُغلق: #497 يتخطّى SMS قناةَ Twilio بلا بيانات اعتماد بدل رفع استثناءٍ يوميّ إلى Sentry.",
    ),
    (
        "DBT-30",
        ("todo", 0),
        "done",
        100,
        "#499",
        "أُغلق: #499 اختباراتُ عرضٍ لقاعدة السنة الأولى (بلا تعديل كود).",
    ),
    (
        "DBT-13",
        ("todo", 0),
        "blocked",
        0,
        "",
        "محجوب: يحتاج لوحةَ Sentry (أعلى الأحداث حجماً واستهلاكَ الحصّة) وهي عند المالك. "
        "المصادرُ المعروفة أُصلحت عند جذرها: Cron مستثنى، وTwilio في #497.",
    ),
    (
        "DBT-14",
        ("todo", 0),
        "blocked",
        0,
        "",
        "محجوب: التشخيصُ الأصليّ خاطئ — المصدرُ /health/ (core/views_health.py:67) يفحص الخطَّ عمداً "
        "منذ حادثة 2026-09-17 ولا عطب، و/health/ يردّ static:ok. الأحداثُ الـ2.3K الأرجحُ من نشراتٍ "
        "سابقة؛ ينتظر تأكيدَ المالك من Sentry أنّ التكرار توقّف.",
    ),
]

# عملٌ دُمج بلا بندٍ في الخارطة: (الرمز، المسار، العنوان، طلب الدمج)
NEW_ITEMS = [
    (
        "N-015",
        "frontend",
        "قوائمُ الشريط الطويلة بأعمدة — نظيرُ لوحة الإدارة، وتصحيحُ تصنيف عناصرها",
        "#486",
    ),
    ("N-016", "ops", "خوادمُ الجلسات تنتظر قاعدةَ البيانات قبل أن تبدأ", "#495"),
    ("N-017", "frontend", "لوحةُ منسّق ومعلّم: جدولي الحقيقيّ، وقائمةُ إدارةٍ كاملة", "#496"),
    (
        "N-018",
        "frontend",
        "الفوتر سطرٌ واحد على الحاسوب وإلصاقُ الذيل بأسفل النافذة في الجدول العامّ",
        "#500",
    ),
    ("N-019", "sec", "الإدارة: عزلُ المدارس في 14 نموذجاً يصل إليها المدير + حارسٌ بنيويّ", "#501"),
    ("N-020", "sec", "الإدارة: المديرُ يعدّل «المدرسة» ولا يضيفها ولا يحذفها", "#502"),
    ("N-021", "frontend", "الإدارة: فوترُ لوحة الإدارة مطابقٌ لفوتر المنصّة الجديد", "#503"),
]

NEW_ITEMS_FIRST_ORDER = 440  # بعد N-014 (439)


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
        ("roadmap", "0005_sync_items_2026_09_23b"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
