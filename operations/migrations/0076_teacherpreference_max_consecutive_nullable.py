"""سقفُ التتالي الشخصيّ يقبل NULL (= العامّ) وافتراضُه NULL لا ٣ (W-20261003-037).

توسيعٌ بلا نقص: لا تُغيَّر قيمٌ قائمة (الإنتاج بلا صفوف تفضيل وقتَ القياس)، وتفريغُ الافتراضيّ في الحقل وحدَه.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0075_decision_basis_direct_entry"),
    ]

    operations = [
        migrations.AlterField(
            model_name="teacherpreference",
            name="max_consecutive",
            field=models.PositiveIntegerField(
                blank=True,
                default=None,
                help_text="فارغٌ يعني السقفَ العامّ للمدرسة — وأيُّ قيمةٍ أعلى منه تُرخي HC5 لهذا المعلّم وتُسجَّل",
                null=True,
                verbose_name="أقصى حصص متتالية",
            ),
        ),
    ]
