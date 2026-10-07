"""قيدا تداخل الحصّة على **الحقيقيّة وحدَها** (W-20261005-006، قرارُ المالك D-219م: حمايةُ الحقيقيّة من الإسقاط الصامت أيّاً كان مولِّدُها).

القيدان القديمان (`no_teacher_time_overlap` و`no_class_time_overlap`) يشملان كلَّ صفّ، فلو وُجدت مؤقّتةٌ في خانةٍ ثمّ وُلّدت لها حصّةٌ حقيقيّةٌ
أسقطتها `bulk_create(ignore_conflicts=True)` **بصمتٍ** — وكانت الحقيقيّةُ هي المفقودة. فيُستبدلان بنسختين مشروطتين بـ`provisional=False`:
الحمايةُ للصفوف غير المؤقّتة **مطابقةٌ حرفاً** (الحقولُ نفسُها)، والمؤقّتةُ تحميها قيودُها الخاصّةُ في 0070.

الترتيبُ: **البديلان أوّلاً ثمّ حذفُ القديمين** في الهجرة نفسها — فلا لحظةَ بلا حمايةٍ على الحقيقيّة. والهجرةُ **عكوسة**: عكسُها يعيد القديمين أوّلاً ثمّ يحذف
البديلين؛ وإن وُجدت مؤقّتةٌ تصادم حقيقيّةً فالعكسُ يفشل بسببٍ مكتوب (`ensure_reversible`) لا بخطأ قيدٍ مبهم — يُغلَق التصادمُ أوّلاً.
والجدولُ في هذا الإصدار بلا مؤقّتات (المفتاحُ مطفأ)، فلا يتغيّر شيءٌ على بيانات الإنتاج.
"""

from django.db import migrations, models


def _noop(apps, schema_editor):
    return None


def ensure_reversible(apps, schema_editor):
    """يعمل عند العكس وحدَه قبل إعادة القيدين الشاملين: صفٌّ مؤقّتٌ يصادم صفّاً آخر في الخانة نفسِها يمنع إعادتَهما."""
    session = apps.get_model("operations", "Session")
    from django.db.models import Count

    clashes = (
        session.objects.values("teacher_id", "date", "start_time")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
        .count()
        + session.objects.values("class_group_id", "date", "start_time", "elective_group")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
        .count()
    )
    if clashes:
        raise RuntimeError(
            f"لا يُعكس 0071: {clashes} خانةً فيها حصّتان (مؤقّتةٌ وحقيقيّة) — أغلِق المؤقّتات المتصادمة أوّلاً ثمّ أعِد العكس."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0070_session_provisional"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="session",
            constraint=models.UniqueConstraint(
                condition=models.Q(("provisional", False)),
                fields=("teacher", "date", "start_time"),
                name="no_teacher_time_overlap_real",
            ),
        ),
        migrations.AddConstraint(
            model_name="session",
            constraint=models.UniqueConstraint(
                condition=models.Q(("provisional", False)),
                fields=("class_group", "date", "start_time", "elective_group"),
                name="no_class_time_overlap_real",
            ),
        ),
        migrations.RemoveConstraint(model_name="session", name="no_teacher_time_overlap"),
        migrations.RemoveConstraint(model_name="session", name="no_class_time_overlap"),
        # آخرُ العمليّات فيُنفَّذ **أوّلَ** العكس: يفحص قبل إعادة القيدين الشاملين.
        migrations.RunPython(_noop, ensure_reversible),
    ]
