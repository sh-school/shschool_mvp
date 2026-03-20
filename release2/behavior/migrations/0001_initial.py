"""
behavior/migrations/0001_initial.py
نقل BehaviorInfraction و BehaviorPointRecovery من core إلى behavior
"""
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('core', '0007_auto_latest'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='BehaviorInfraction',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('date', models.DateField(auto_now_add=True)),
                        ('created_at', models.DateTimeField(auto_now_add=True, null=True)),
                        ('level', models.PositiveSmallIntegerField(choices=[(1,'الدرجة الأولى (بسيطة)'),(2,'الدرجة الثانية (متوسطة)'),(3,'الدرجة الثالثة (جسيمة)'),(4,'الدرجة الرابعة (شديدة الخطورة)')], default=1)),
                        ('description', models.TextField(verbose_name='وصف المخالفة')),
                        ('action_taken', models.TextField(blank=True, verbose_name='الإجراء المتخذ')),
                        ('points_deducted', models.PositiveIntegerField(default=0, verbose_name='النقاط المخصومة')),
                        ('is_resolved', models.BooleanField(default=False)),
                        ('reported_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reported_infractions', to='core.customuser')),
                        ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.school')),
                        ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='behavior_infractions', to='core.customuser')),
                    ],
                    options={'verbose_name': 'مخالفة سلوكية', 'verbose_name_plural': 'المخالفات السلوكية', 'ordering': ['-date', '-created_at'], 'db_table': 'core_behaviorinfraction'},
                ),
                migrations.CreateModel(
                    name='BehaviorPointRecovery',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('reason', models.TextField(verbose_name='سبب استعادة النقاط (سلوك إيجابي)')),
                        ('points_restored', models.PositiveIntegerField(default=0)),
                        ('date', models.DateField(auto_now_add=True)),
                        ('approved_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.customuser')),
                        ('infraction', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='recovery', to='behavior.behaviorinfraction')),
                    ],
                    options={'verbose_name': 'استعادة نقاط', 'verbose_name_plural': 'استعادة النقاط', 'db_table': 'core_behaviorpointrecovery'},
                ),
            ],
            database_operations=[],
        ),
    ]
