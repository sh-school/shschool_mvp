"""جدولُ الشعبة العموديّ لرصد الغياب (W-20261006-005، قرارا المالك D-239م وD-240م) — هجرةٌ واحدةٌ صغيرةٌ عكوسة.

1. إزالةُ `provisional_teacher_period_unique`: عمودُ الجدول يُنسب لمُسنَدٍ حتميّ فيصادمه كاتبٌ يحفظ ح1 لعدّة شعب. (يمسّ صفوفَ المؤقّتة وحدَها.)
2. استبدالُ `provisional_class_period_unique` بنسخةٍ تحمل `elective_group` (مراجعة 0102): الصفوفُ القائمةُ كلُّها بمجموعةٍ فارغةٍ
   وفريدةٍ أصلاً بـ(شعبة، تاريخ، رقم) فالقيدُ الجديدُ يمرّ عليها. الإزالةُ والإضافةُ في المعاملة نفسِها (سابقة 0071).
3. `AttendanceEntry.origin` — توسيعٌ بـ`db_default` فلا تفشل نسخةُ الكود القديمةُ أثناء النشر المتدحرج.
4. `AlterField` لخيارات `AttendanceDecision.basis` بإضافة `wing_holder_self` (قائمةُ اختيارٍ بلا SQL).

العكسُ يفشل بسببٍ مكتوبٍ إن وُجدت مؤقّتتان لمعلّمٍ واحدٍ في الخانة نفسِها (يمنعان إعادةَ قيد المعلّم) — تُغلق إحداهما أوّلاً.
"""

from django.conf import settings
from django.db import migrations, models


def _noop(apps, schema_editor):
    return None


def ensure_reversible(apps, schema_editor):
    """يعمل عند العكس وحدَه قبل إعادة قيد (المعلّم، التاريخ، الرقم) المؤقّت: يمنعه صفٌّ مكرَّرٌ."""
    from django.db.models import Count

    session = apps.get_model("operations", "Session")
    clashes = (
        session.objects.filter(provisional=True)
        .values("teacher_id", "date", "period_number")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
        .count()
    )
    if clashes:
        raise RuntimeError(
            f"لا يُعكس 0073: {clashes} خانةً فيها مؤقّتتان لمعلّمٍ واحد — أغلِق إحداهما أوّلاً ثمّ أعِد العكس."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0079_capability_grant_wings_school_wide"),
        ("operations", "0072_decision_basis_school_wide"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="session",
            name="provisional_class_period_unique",
        ),
        migrations.RemoveConstraint(
            model_name="session",
            name="provisional_teacher_period_unique",
        ),
        migrations.AddField(
            model_name="attendanceentry",
            name="origin",
            field=models.CharField(
                blank=True,
                db_default="",
                default="",
                max_length=16,
                verbose_name="مصدرُ الإدخال",
            ),
        ),
        migrations.AlterField(
            model_name="attendancedecision",
            name="basis",
            field=models.CharField(
                choices=[
                    ("wing_holder", "حاملُ جناح الشعبة"),
                    ("leadership_no_holder", "القيادةُ — لا حاملَ للجناح"),
                    (
                        "leadership_holder_is_teacher",
                        "القيادةُ — حاملُ الجناح هو معلّمُ الحصّة",
                    ),
                    (
                        "leadership_holder_inactive",
                        "القيادةُ — حاملُ الجناح بلا عضويّةٍ نشطة",
                    ),
                    ("school_wide", "حاصرُ الغياب العامّ — اعتمادٌ ثانٍ بجانب الحامل"),
                    ("supervisor_record", "كُتب رصدُ مشرفٍ فوق الإدخال"),
                    ("special_ed_self", "التربيةُ الخاصّة — اعتمادٌ ذاتيٌّ بالتصميم"),
                    (
                        "wing_holder_self",
                        "حاملُ الجناح — اعتمادُ ما كتبه بنفسه (جدولُ الشعبة)",
                    ),
                ],
                max_length=40,
                verbose_name="أساسُ الصلاحيّة",
            ),
        ),
        migrations.AddConstraint(
            model_name="session",
            constraint=models.UniqueConstraint(
                condition=models.Q(("provisional", True)),
                fields=("class_group", "date", "period_number", "elective_group"),
                name="provisional_class_period_unique",
            ),
        ),
        # آخرُ العمليّات فيُنفَّذ **أوّلَ** العكس: يفحص قبل إعادة القيد.
        migrations.RunPython(_noop, ensure_reversible),
    ]
