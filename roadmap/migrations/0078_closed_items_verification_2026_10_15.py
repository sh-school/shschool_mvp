"""الخارطةُ الثالثةُ والستّون (2026-10-15): نتيجةُ تحقّق الجلسة 0701 من اثني عشر بنداً مغلقاً (أمر المالك، قراءةٌ فقط على الإنتاج a6ab9f4).

لا بندَ يُعاد فتحُه ولا حالةَ تتغيّر. ثلاثةُ تعديلات: (1) تصحيحُ صياغة N-117 وفق D-221م (العملُ صحيح والعنوانُ معكوس)،
(2) مرجعُ DBT-40 وDBT-42: #560 وحارسُ DOCUMENTS_ONLY، (3) ملاحظاتُ تحفّظٍ على OWN-15 وOWN-21 وVI-25 وDBT-14.
حارسةٌ: لا يُمَسّ بندٌ غابَ أو عدّله المطوّرُ (العنوانُ يُصحَّح فقط إن بقي نصَّه القديم)، ولا ملاحظةَ تتكرّر.
**المقيسُ قراءةً عند 0701 لا وظيفياً:** ما يحتاج حساباً على الإنتاج (صفحاتُ الإدارة وPDF الزيارة وaxe) لم يُقَس.
**المستودعُ عامّ:** نصوصٌ محايدةٌ بلا أسماءٍ ولا مفاتيح.
"""

from django.db import migrations

STAMP = "[2026-10-15]"

N117_OLD = "PDF استمارة الزيارة الصفّية: عبارة «توقيعٌ إلكترونيّ داخل المنصّة» ووقت الختم في الخانتين (D-221م)"
N117_TITLE = "PDF استمارة الزيارة الصفّية: خانتا التوقيع تطبعان الاسمَ وحدَه بلا عبارةٍ ولا وقتِ ختم (D-221م)"
N117_CRITERION = "خانتا التوقيع في PDF الزيارة تطبعان الاسمَ وحدَه، وغيابُ العبارة ووقتِ الختم مثبتٌ باختبار."
N117_NOTE = (
    "صُحّحت الصياغة: قرارُ D-221م يحذف العبارةَ ووقتَ الختم لا يُظهرهما؛ والعملُ (#948) صحيح ومثبتٌ باختبار test_observation_pdf_a4. "
    "المقيسُ قراءةً عند 0701 على الإنتاج a6ab9f4؛ ناتجُ PDF على الإنتاج لم يُقَس."
)

# (الرمز، الطلب، المرجع، الملاحظة) — المرجعُ يُكتب إن كان فارغاً فقط.
REFERENCES = [
    (
        "DBT-40",
        "#560",
        "tests/test_uploads_are_photo_cleaned.py::DOCUMENTS_ONLY؛ staff_affairs/views.py::leave_request_create",
        "أُكمل المرجع: حارسُ DOCUMENTS_ONLY من #560 (في الإنتاج) يغطّي مرفقَ LeaveRequestForm. الإغلاقُ «لا دَين» لا «منجز» ولم تتغيّر حالتُه. المقيسُ قراءةً عند 0701.",
    ),
    (
        "DBT-42",
        "#560",
        "tests/test_uploads_are_photo_cleaned.py::DOCUMENTS_ONLY؛ student_affairs/views.py::activity_add وactivity_edit",
        "أُكمل المرجع: حارسُ DOCUMENTS_ONLY من #560 (في الإنتاج) يغطّي مرفقَ ActivityForm في الإضافة والتعديل. الإغلاقُ «لا دَين» لا «منجز» ولم تتغيّر حالتُه. المقيسُ قراءةً عند 0701.",
    ),
]

# ملاحظاتُ تحفّظٍ فقط (لا تغيير حالةٍ): (الرمز، النص).
RESERVATIONS = [
    ("OWN-15", "تحقّق 0701 (قراءة، الإنتاج a6ab9f4): list_per_page = 25 واختبارُ القائمة موجودان في الإنتاج. **لم يُقَس:** صفحاتُ الإدارة الفعليّة (تحتاج حساباً) والوضعُ الليليّ."),
    ("OWN-21", "تحقّق 0701 (قراءة): admin_theme.css المنشورُ على الإنتاج يحوي --adm-control-h: 44px. **تحفّظ:** الفحصُ الليليّ كان عيّنةَ ستّ صفحاتٍ لا كلَّ الصفحات."),
    ("VI-25", "تحقّق 0701 (قراءة): رابطُ «غير المقروء فقط» يحمل aria-current في قالب الصندوق على الإنتاج. **لم يُقَس:** نتيجةُ axe الفعليّة على الإنتاج."),
    ("DBT-14", "تحقّق 0701 (قراءة Sentry): آخرُ ظهورٍ للمسألة 2026-09-17 ولا حدثَ منذ 28 يوماً، ومدخلُ manifest للخط موجودٌ والخطُّ يُخدَم 200. **السببُ الجذريّ غيرُ مثبت** كما في البند."),
]


def _add_pr(existing, token):
    """تُضيف رمزَ الطلب دون تكرارٍ ودون تجاوز حدّ الحقل 64 (وإلّا يبقى الحقلُ كما هو)."""
    if not token:
        return existing
    joined = " ".join(dict.fromkeys([*existing.split(), *token.split()]))
    return joined if len(joined) <= 64 else existing


def _append_note(item, text):
    """تُلحق ملاحظةً مختومةً مرّةً واحدة؛ تُرجع هل تغيّر الحقل."""
    if text in item.note:
        return False
    item.note = f"{item.note}\n{STAMP} {text}".strip()
    return True


def fix_n117(item_model):
    item = item_model.objects.filter(code="N-117").first()
    if item is None or item.title != N117_OLD:
        return []
    item.title = N117_TITLE
    item.criterion = N117_CRITERION
    _append_note(item, N117_NOTE)
    item.save(update_fields=["title", "criterion", "note", "updated_at"])
    return ["N-117"]


def complete_references(item_model):
    done = []
    for code, pr, ref, note in REFERENCES:
        item = item_model.objects.filter(code=code).first()
        if item is None:
            continue
        fields = []
        if not item.ref:
            item.ref = ref
            fields.append("ref")
        new_pr = _add_pr(item.pr, pr)
        if new_pr != item.pr:
            item.pr = new_pr
            fields.append("pr")
        if _append_note(item, note):
            fields.append("note")
        if fields:
            item.save(update_fields=[*fields, "updated_at"])
            done.append(code)
    return done


def add_reservations(item_model):
    done = []
    for code, text in RESERVATIONS:
        item = item_model.objects.filter(code=code).first()
        if item is None or not _append_note(item, text):
            continue
        item.save(update_fields=["note", "updated_at"])
        done.append(code)
    return done


def forwards(apps, schema_editor):
    item_model = apps.get_model("roadmap", "RoadmapItem")
    # قاعدةٌ بلا استيراد (اختبار، شجرةٌ جديدة): لا شيء يُزامَن.
    if not item_model.objects.exists():
        return
    fix_n117(item_model)
    complete_references(item_model)
    add_reservations(item_model)


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0077_sync_items_2026_10_14"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
