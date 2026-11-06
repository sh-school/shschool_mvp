from django.db import migrations

# نصّ معيار خطة الدرس: القديم (نظام قطر للتعليم) والجديد (كما في نموذج التوجيه التربوي 2024-2025).
OLD_TEXT = "خطة الدرس متوفرة وبنودها مستكملة ومناسبة ومعلنة على نظام قطر للتعليم."
NEW_TEXT = "خطة الدرس متوفرة وبنودها مستكملة ومناسبة ومعلنة على منصّة التعلّم الإلكتروني."


def _retext(apps, old, new):
    """يُحدِّث نصَّ الصفوف نفسها (لا يُنشئ صفّاً) فتبقى درجات الزيارات السابقة مرتبطةً بها.

    إن وُجد لمدرسةٍ ما صفٌّ بالنصّ الجديد في المجال نفسه، يُترك الصفّ القديم كما هو:
    تحديثُه سيخرق القيد الفريد (school, domain, text)، وحذفُه يمسّ الدرجات. لا يحدث هذا
    اليوم لأن الزرع لم يُنتج النصّ الجديد قطّ.
    """
    ObservationCriterion = apps.get_model("quality", "ObservationCriterion")
    for row in ObservationCriterion.objects.filter(text=old):
        clash = ObservationCriterion.objects.filter(
            school_id=row.school_id, domain=row.domain, text=new
        ).exists()
        if not clash:
            ObservationCriterion.objects.filter(pk=row.pk).update(text=new)


def forward(apps, schema_editor):
    _retext(apps, OLD_TEXT, NEW_TEXT)


def backward(apps, schema_editor):
    _retext(apps, NEW_TEXT, OLD_TEXT)


class Migration(migrations.Migration):
    """تحديثُ بيانات فقط (W-20261106-012): نصُّ معيار خطة الدرس يتبع نموذج التوجيه التربوي.

    seed_observation_criteria يعمل بـ get_or_create على النصّ، فتغييرُ النصّ في الزرع وحده
    كان سيُنشئ معياراً رابعاً وعشرين عند إعادة التشغيل. هذه الهجرة تُحدِّث الصفوف القائمة
    لتطابق النصّ الجديد قبل أن يُعدَّل الزرع. العكس يعيد النصّ القديم بلا أثر.
    """

    dependencies = [
        ("quality", "0024_classroomobservation_outside_schedule"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
