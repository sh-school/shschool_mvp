import operations.models.schedule
from django.db import migrations, models


class Migration(migrations.Migration):
    """يسمح بالصفر في `max_last_periods` (منعُ السابعة عن معلّمٍ بعينه، W-20261004-013).

    تغييرُ validators ونصِّ مساعدةٍ فقط: لا SQL ولا لمسَ لبيانات قائمة، ولا إعادةَ تفسيرٍ لما خُزّن.
    """

    dependencies = [
        ("operations", "0080_rls_schedule_relaxation_policy"),
    ]

    operations = [
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
