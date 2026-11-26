"""الخارطة (2026-11-26): تسجيلُ استمارة 19 «متابعة أداء المشرف الإداري» (#1520 و#1521) منجزةً ومنشورة.

حارسةٌ كسابقاتها: لا يُنشأ البندُ إن حمل بندٌ قائمٌ أحدَ رقمَي الطلبين، ولا يُلمس بندٌ قائم.
**التغطية:** لا بندَ في هجرات الخارطة يغطّي الاستمارة، فهي بندُ N- جديدٌ بأوّل رمزٍ شاغرٍ من N-174 فصاعداً.
**المقيس:** الطلبان مدموجان في main (سجلّ git)، والنشرُ 2026-11-26 بحسب بطاقة العمل.
**لم يُقَس** الاستعمالُ الفعليّ في المدرسة ولا السلوكُ بجلسةٍ حقيقيّة على الإنتاج.
**المستودعُ عامّ:** نصوصٌ محايدةٌ بلا أسماءٍ ولا مضيفات.
"""

import datetime

from django.db import migrations

FIRST_N = 174
PRS = "#1520 #1521"
TITLE = "استمارة 19 متابعة أداء المشرف الإداري"
CRITERION = "لوحةُ إدخال المتابعة وطباعتُها؛ وإرسالُها للمشرف وإقرارُه بها والتوقيعان."
NOTE = (
    "[2026-11-26] **بندٌ جديد، منجزٌ ومنشورٌ 2026-11-26.** #1520 لوحةُ الإدخال والطباعة، ثمّ #1521 الإرسالُ "
    "والإقرار. **المقيس:** الطلبان مدموجان في main والنشرُ بحسب بطاقة العمل. "
    "**لم يُقَس** الاستعمالُ الفعليّ في المدرسة ولا السلوكُ بجلسةٍ حقيقيّةٍ على الإنتاج."
)

_DAY = datetime.date(2026, 11, 26)


def _free_n_code(item_model):
    """أوّلُ رمز N- شاغرٍ من FIRST_N فصاعداً."""
    n = FIRST_N
    while item_model.objects.filter(code=f"N-{n}").exists():
        n += 1
    return f"N-{n}"


def add_item(item_model):
    """تُنشئ البندَ مرّةً واحدة؛ تُرجع رمزَه، أو None إن كان أحدُ الطلبين مسجَّلاً."""
    if any(item_model.objects.filter(pr__contains=token).exists() for token in PRS.split()):
        return None
    code = _free_n_code(item_model)
    item_model.objects.create(
        code=code,
        src="N",
        lane="product",
        title=TITLE,
        status="done",
        progress=100,
        start_date=_DAY,
        end_date=_DAY,
        date_basis="اندمج ونُشر؛ سُجّل 2026-11-26",
        effort=1.0,
        deps="",
        criterion=CRITERION,
        gate="",
        pr=PRS,
        ref="",
        note=NOTE,
        sort_order=915,
    )
    return code


def forwards(apps, schema_editor):
    item_model = apps.get_model("roadmap", "RoadmapItem")
    # قاعدةٌ بلا استيراد (اختبار، شجرةٌ جديدة): لا شيء يُزامَن.
    if not item_model.objects.exists():
        return
    add_item(item_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0091_sync_items_2026_11_24"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
