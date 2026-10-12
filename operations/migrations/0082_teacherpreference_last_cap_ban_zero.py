from django.db import migrations, models

import operations.models.schedule


def zero_to_general(apps, schema_editor):
    """يحوّل كلَّ صفرٍ قديمٍ في `max_last_periods` إلى `NULL` (السقفِ العامّ) قبل أن يتغيّر معنى الصفر.

    كان الصفرُ في القراءة يعني «خُذ العامّ» (`personal_last_cap`)؛ وبعد W-20261004-013 صار منعاً للسابعة. فأيُّ صفٍّ
    مخزَّنٍ صفراً قبل هذا الإصدار كان حكمُه العامَّ، ويبقى كذلك بتحويله إلى `NULL` — لا منعاً صامتاً عند أوّل توليد
    (قرارُ المالك D-413م، شرطُ 0104). idempotent (إعادةُ التشغيل لا تجد صفراً)، وتعمل ولو لم يوجد صفرٌ أصلاً.
    ولا تمسّ سوى هذا العمود: لا جدولاً معتمداً ولا قيمةً أخرى (D-381م).
    """
    preference = apps.get_model("operations", "TeacherPreference")
    preference.objects.filter(max_last_periods=0).update(max_last_periods=None)


def _noop(apps, schema_editor):
    """لا عكسَ للبيانات: لا يُعرف أيُّ الفارغات كانت أصفاراً."""
    return None


class Migration(migrations.Migration):
    """يسمح بالصفر في `max_last_periods` (منعُ السابعة عن معلّمٍ بعينه، W-20261004-013).

    الخطوة الأولى بياناتٌ: الأصفارُ القديمة (= العامّ) تصير `NULL` قبل أن يصير الصفرُ منعاً. والثانية تغييرُ
    validators ونصِّ مساعدةٍ فقط بلا SQL.
    """

    dependencies = [
        ("operations", "0081_absence_excuse_form04"),
    ]

    operations = [
        migrations.RunPython(zero_to_general, _noop),
        migrations.AlterField(
            model_name="teacherpreference",
            name="max_last_periods",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="قرارٌ إداريّ في حقّ هذا المعلّم: أقصى عدد حصص السابعة في الأسبوع (2 هو السقفُ العامّ، و0 يمنع السابعة عنه)",
                null=True,
                validators=[operations.models.schedule.validate_admin_last_cap],
                verbose_name="أقصى سابعات أسبوعيّاً",
            ),
        ),
    ]
