"""
Migration: Phase 6 — تقييم الموظفين
القرار الأميري 9/2016 + قانون 9/2017
"""
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('quality', '0001_initial'),
        ('core', '0007_add_security_and_consent_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='EvaluationCycle',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ('academic_year', models.CharField(default='2025-2026', max_length=9)),
                ('period', models.CharField(choices=[('S1', 'نهاية الفصل الأول'), ('S2', 'نهاية العام الدراسي')], max_length=2)),
                ('deadline', models.DateField(verbose_name='الموعد النهائي للتقييم')),
                ('is_closed', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='eval_cycles', to='core.school')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.customuser')),
            ],
            options={'verbose_name': 'دورة تقييم', 'verbose_name_plural': 'دورات التقييم'},
        ),
        migrations.CreateModel(
            name='EmployeeEvaluation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ('academic_year', models.CharField(default='2025-2026', max_length=9)),
                ('period', models.CharField(choices=[('S1', 'نهاية الفصل الأول'), ('S2', 'نهاية العام الدراسي')], max_length=2, verbose_name='الفترة')),
                ('status', models.CharField(choices=[('draft', 'مسودة'), ('submitted', 'مُقدَّم'), ('approved', 'مُعتمد'), ('acknowledged', 'مُستلم من الموظف')], default='draft', max_length=15)),
                ('axis_professional', models.PositiveSmallIntegerField(default=0, verbose_name='الكفاءة المهنية (25)')),
                ('axis_commitment', models.PositiveSmallIntegerField(default=0, verbose_name='الالتزام والمسؤولية (25)')),
                ('axis_teamwork', models.PositiveSmallIntegerField(default=0, verbose_name='العمل الجماعي والتواصل (25)')),
                ('axis_development', models.PositiveSmallIntegerField(default=0, verbose_name='التطوير المهني والمبادرة (25)')),
                ('total_score', models.PositiveSmallIntegerField(default=0, verbose_name='المجموع الكلي')),
                ('rating', models.CharField(blank=True, choices=[('excellent', 'ممتاز (90–100)'), ('very_good', 'جيد جداً (75–89)'), ('good', 'جيد (60–74)'), ('needs_dev', 'يحتاج تطوير (أقل من 60)')], max_length=15)),
                ('strengths', models.TextField(blank=True, verbose_name='نقاط القوة')),
                ('improvements', models.TextField(blank=True, verbose_name='مجالات التطوير')),
                ('goals_next', models.TextField(blank=True, verbose_name='أهداف الفترة القادمة')),
                ('employee_comment', models.TextField(blank=True, verbose_name='تعليق الموظف')),
                ('acknowledged_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='evaluations', to='core.school')),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='evaluations', to='core.customuser', verbose_name='الموظف')),
                ('evaluator', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='evaluations_given', to='core.customuser', verbose_name='المقيِّم')),
            ],
            options={'verbose_name': 'تقييم موظف', 'verbose_name_plural': 'تقييمات الموظفين', 'ordering': ['-created_at']},
        ),
        migrations.AddConstraint(
            model_name='employeeevaluation',
            constraint=models.UniqueConstraint(fields=['school', 'employee', 'academic_year', 'period'], name='unique_eval_per_period'),
        ),
        migrations.AddConstraint(
            model_name='evaluationcycle',
            constraint=models.UniqueConstraint(fields=['school', 'academic_year', 'period'], name='unique_eval_cycle'),
        ),
    ]
