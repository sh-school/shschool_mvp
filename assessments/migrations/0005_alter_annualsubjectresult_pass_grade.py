# Generated manually 2026-03-27 — تغيير درجة النجاح من 50 إلى 60 حسب مواصفات وزارة التعليم القطرية

from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assessments', '0004_alter_subjectclasssetup_teacher'),
    ]

    operations = [
        migrations.AlterField(
            model_name='annualsubjectresult',
            name='pass_grade',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('60'),
                max_digits=5,
                verbose_name='درجة النجاح',
            ),
        ),
    ]
