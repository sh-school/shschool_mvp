"""
behavior/migrations/0002_violationcategory_abcd.py
✅ إضافة نموذج ViolationCategory (لائحة ABCD)
✅ إضافة ForeignKey في BehaviorInfraction
"""
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('behavior', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ViolationCategory',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('category', models.CharField(
                    choices=[('A', 'الفئة A — خفيفة'), ('B', 'الفئة B — متوسطة'),
                             ('C', 'الفئة C — جسيمة'), ('D', 'الفئة D — حرجة')],
                    max_length=1, verbose_name='الفئة'
                )),
                ('code', models.CharField(max_length=3, unique=True, verbose_name='الرمز (A1-D5)')),
                ('name_ar', models.CharField(max_length=200, verbose_name='اسم المخالفة')),
                ('default_action', models.CharField(blank=True, max_length=300, verbose_name='الإجراء الافتراضي')),
                ('points', models.PositiveSmallIntegerField(default=5, verbose_name='النقاط المخصومة')),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'فئة مخالفة سلوكية',
                'verbose_name_plural': 'فئات المخالفات السلوكية (ABCD)',
                'ordering': ['category', 'code'],
            },
        ),
        migrations.AddField(
            model_name='behaviorinfraction',
            name='violation_category',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='infractions',
                to='behavior.violationcategory',
                verbose_name='فئة المخالفة (ABCD)',
            ),
        ),
    ]
