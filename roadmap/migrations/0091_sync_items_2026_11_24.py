"""الخارطة (2026-11-24): تسجيلُ ما اندمج بعد 0090 — الانتقال، المشرف الميدانيّ، تبديل الحصص، إصلاحات 11-21، تثبيت sentry-sdk.

حارسةٌ كسابقاتها: الملاحظةُ لا تتكرّر، ورمزُ الطلب يُضاف دون تكرارٍ ودون تجاوز حدّ الحقل 64 (`_add_pr`)،
ولا حالةَ أو تقدّمَ لبندٍ قائمٍ يُلمس، ولا يُعاد إنشاءُ بندٍ يحمل رقمَ طلبه.
**التغطية:** تطابقُ المشرف الميدانيّ مع مشرف الجناح (#1499 و#1508) ملاحظةٌ على WNG-01 القائم؛ والبقيّةُ بنودُ N- جديدةٌ
بأوّل رمزٍ شاغرٍ من N-170 فصاعداً (الصفحةُ تولّد رموز N- أيضاً فلا يُثبَّت رقمٌ).
**المقيس:** الطلباتُ مدموجةٌ في main (سجلّ git). **لم يُقَس** الاستعمالُ الفعليّ في المدرسة ولا السلوكُ بجلسةٍ حقيقيّة على الإنتاج.
لا بندَ مُغلقٌ بلا رقم طلبه، ولا بندَ يُوسَم منجزاً وهو ينتظر بيانَ المالك.
**المستودعُ عامّ:** نصوصٌ محايدةٌ بلا أسماءٍ ولا مضيفات.
"""

import datetime

from django.db import migrations

STAMP = "[2026-11-24]"
FIRST_N = 170

_DAY = datetime.date(2026, 11, 24)
_BASIS = "اندمج في main بعد 0090؛ سُجّل 2026-11-24 من سجلّ الدمج"
_MEASURED = (
    "**المقيس (2026-11-24):** الطلباتُ المذكورةُ مدموجةٌ في main. "
    "**لم يُقَس** الاستعمالُ الفعليّ في المدرسة ولا السلوكُ بجلسةٍ حقيقيّةٍ على الإنتاج."
)

# (الرمز، الطلب، الملاحظة) — تُلحق بلا لمس الحالة أو التقدّم
NOTES = [
    (
        "WNG-01",
        "#1499 #1508",
        "اندمج #1499 ثم #1508 بعد 0090: المشرفُ الميدانيّ يتطابق مع مشرف الجناح في الواجهة والقدرات. "
        + _MEASURED,
    ),
]

# (المسار، العنوان، المعيار، الطلبات، الملاحظة، ترتيبُ الفرز)
NEW_ITEMS = [
    (
        "product",
        "تحسينُ نموذج الانتقال: بحثُ الطالب، وملخّصُ الاتجاه، ومراجعةُ النقل المباشر، والتحقّقُ الموحَّد",
        "حقلُ بحث الطالب بقائمةٍ منسدلةٍ احترافيّة ورسالةِ منعٍ واضحة؛ ملخّصُ اتجاه الانتقال قبل الإرسال؛ "
        "مراجعةٌ للنقل المباشر قبل التنفيذ؛ وتحقّقٌ موحَّدٌ للنموذج.",
        "#1509 #1510",
        "**بندٌ جديد.** عملٌ على نموذج الانتقال على دفعتين: #1509 بحثُ الطالب، ثمّ #1510 ملخّصُ الاتجاه ومراجعةُ "
        "النقل المباشر والتحقّقُ الموحَّد. " + _MEASURED,
        911,
    ),
    (
        "product",
        "تبديلُ الحصص: مهلةُ 45 دقيقة وإلغاءُ الطلبات المعلّقة",
        "طلبُ التبديل له مهلةٌ مدّتها 45 دقيقة؛ وللطلب المعلّق إلغاءٌ.",
        "#1496 #1497",
        "**بندٌ جديد.** #1496 و#1497 على تبديل الحصص: مهلةُ 45 دقيقة وإلغاءُ المعلّقة. " + _MEASURED,
        912,
    ),
    (
        "product",
        "إصلاحاتُ 2026-11-21: حزمةُ طلباتٍ من #1491 إلى #1495",
        "خمسةُ طلباتِ إصلاحٍ مدموجةٌ (#1491 و#1492 و#1493 و#1494 و#1495) بأرقامها.",
        "#1491 #1492 #1493 #1494 #1495",
        "**بندٌ جديد.** تسجيلٌ لحزمة إصلاحات 11-21 بأرقام طلباتها؛ تفاصيلُ كلّ طلبٍ في سجلّ الدمج. "
        + _MEASURED,
        913,
    ),
    (
        "ops",
        "تثبيتُ sentry-sdk دون الإصدار 3 بعد انكسار CI",
        "اعتماديّةُ sentry-sdk مقيّدةٌ بما دون الإصدار 3 فيعود CI سليماً.",
        "#1505",
        "**بندٌ جديد.** #1505: التثبيتُ دون الإصدار 3 بعد انكسار CI. " + _MEASURED,
        914,
    ),
]


def _add_pr(existing, token):
    """تُضيف رمزَ الطلب دون تكرارٍ ودون تجاوز حدّ الحقل 64 (وإلّا يبقى الحقلُ كما هو)."""
    if not token:
        return existing
    joined = " ".join(dict.fromkeys([*existing.split(), *token.split()]))
    return joined if len(joined) <= 64 else existing


def sync_notes(item_model):
    """تُلحق الملاحظاتِ ورمزَ الطلب بالبنود القائمة مرّةً واحدة بلا لمس الحالة؛ تُرجع رموزَ ما تغيّر."""
    changed = []
    for code, pr, line in NOTES:
        item = item_model.objects.filter(code=code).first()
        if item is None or line in item.note:
            continue
        item.note = f"{item.note}\n{STAMP} {line}".strip()
        item.pr = _add_pr(item.pr, pr)
        item.save(update_fields=["note", "pr", "updated_at"])
        changed.append(code)
    return changed


def _free_n_code(item_model):
    """أوّلُ رمز N- شاغرٍ من FIRST_N فصاعداً."""
    n = FIRST_N
    while item_model.objects.filter(code=f"N-{n}").exists():
        n += 1
    return f"N-{n}"


def add_new_items(item_model):
    """تُنشئ كلَّ بندٍ غاب رقمُ طلبه الأوّل من حقل pr؛ لا تُعيد كتابةَ بندٍ موجود؛ تُرجع رموزَ ما أُنشئ."""
    created = []
    for lane, title, criterion, prs, note, order in NEW_ITEMS:
        if item_model.objects.filter(pr__contains=prs.split()[0]).exists():
            continue
        code = _free_n_code(item_model)
        item_model.objects.create(
            code=code,
            src="N",
            lane=lane,
            title=title,
            status="done",
            progress=100,
            start_date=_DAY,
            end_date=_DAY,
            date_basis=_BASIS,
            effort=1.0,
            deps="",
            criterion=criterion,
            gate="",
            pr=prs,
            ref="",
            note=f"{STAMP} {note}",
            sort_order=order,
        )
        created.append(code)
    return created


def forwards(apps, schema_editor):
    item_model = apps.get_model("roadmap", "RoadmapItem")
    # قاعدةٌ بلا استيراد (اختبار، شجرةٌ جديدة): لا شيء يُزامَن.
    if not item_model.objects.exists():
        return
    sync_notes(item_model)
    add_new_items(item_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0090_sync_notes_2026_11_20"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
