"""
quality/migrations/0001_initial.py
المرحلة 5 — الخطة التشغيلية + لجنة المراجعة الذاتية
"""
import django.db.models.deletion
import quality.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('core', '0001_phase2_schedule_substitute'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [

        migrations.CreateModel(
            name='OperationalDomain',
            fields=[
                ('id',            models.UUIDField(default=quality.models._uuid, editable=False, primary_key=True, serialize=False)),
                ('name',          models.CharField(max_length=200, verbose_name='اسم المجال')),
                ('academic_year', models.CharField(default='2025-2026', max_length=9)),
                ('order',         models.IntegerField(default=0)),
                ('school',        models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='op_domains', to='core.school')),
            ],
            options={'verbose_name': 'مجال', 'verbose_name_plural': 'المجالات', 'ordering': ['order', 'name']},
        ),
        migrations.AddConstraint(
            model_name='operationaldomain',
            constraint=models.UniqueConstraint(fields=['school', 'name', 'academic_year'], name='unique_domain_per_year'),
        ),

        migrations.CreateModel(
            name='OperationalTarget',
            fields=[
                ('id',     models.UUIDField(default=quality.models._uuid, editable=False, primary_key=True, serialize=False)),
                ('number', models.CharField(max_length=20, verbose_name='رقم الهدف')),
                ('text',   models.TextField(verbose_name='نص الهدف')),
                ('domain', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='targets', to='quality.operationaldomain')),
            ],
            options={'verbose_name': 'هدف', 'verbose_name_plural': 'الأهداف', 'ordering': ['number']},
        ),
        migrations.AddConstraint(
            model_name='operationaltarget',
            constraint=models.UniqueConstraint(fields=['domain', 'number'], name='unique_target_in_domain'),
        ),

        migrations.CreateModel(
            name='OperationalIndicator',
            fields=[
                ('id',     models.UUIDField(default=quality.models._uuid, editable=False, primary_key=True, serialize=False)),
                ('number', models.CharField(max_length=30, verbose_name='رقم المؤشر')),
                ('text',   models.TextField(verbose_name='نص المؤشر')),
                ('target', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='indicators', to='quality.operationaltarget')),
            ],
            options={'verbose_name': 'مؤشر', 'verbose_name_plural': 'المؤشرات', 'ordering': ['number']},
        ),

        migrations.CreateModel(
            name='OperationalProcedure',
            fields=[
                ('id',                      models.UUIDField(default=quality.models._uuid, editable=False, primary_key=True, serialize=False)),
                ('number',                  models.CharField(db_index=True, max_length=30, verbose_name='رقم الإجراء')),
                ('text',                    models.TextField(verbose_name='نص الإجراء')),
                ('executor_norm',           models.CharField(db_index=True, max_length=100, verbose_name='المنفذ (نص)')),
                ('date_range',              models.CharField(blank=True, max_length=50, verbose_name='الفترة الزمنية')),
                ('status',                  models.CharField(choices=[('In Progress','قيد التنفيذ'),('Completed','مكتمل'),('Cancelled','ملغى'),('Not Started','لم يبدأ')], db_index=True, default='In Progress', max_length=15)),
                ('evaluation',              models.TextField(blank=True, verbose_name='التقييم')),
                ('evaluation_notes',        models.TextField(blank=True, verbose_name='ملاحظات التقييم')),
                ('follow_up',               models.TextField(blank=True, verbose_name='المتابعة')),
                ('comments',                models.TextField(blank=True, verbose_name='تعليقات')),
                ('evidence_type',           models.CharField(blank=True, choices=[('وصفي','وصفي'),('كمي','كمي'),('كمي/وصفي','كمي/وصفي'),('','—')], max_length=20)),
                ('evidence_source_employee',models.TextField(blank=True, verbose_name='موظف مصدر الدليل')),
                ('evidence_source_file',    models.TextField(blank=True, verbose_name='ملف مصدر الدليل')),
                ('academic_year',           models.CharField(default='2025-2026', max_length=9)),
                ('created_at',              models.DateTimeField(auto_now_add=True)),
                ('updated_at',              models.DateTimeField(auto_now=True)),
                ('indicator',   models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='procedures', to='quality.operationalindicator')),
                ('school',      models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='procedures', to='core.school')),
                ('executor_user',models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_procedures', to=settings.AUTH_USER_MODEL, verbose_name='المنفذ (مستخدم)')),
            ],
            options={'verbose_name': 'إجراء', 'verbose_name_plural': 'الإجراءات', 'ordering': ['number']},
        ),
        migrations.AddIndex(model_name='operationalprocedure', index=models.Index(fields=['school','status'], name='quality_op__school__status_idx')),
        migrations.AddIndex(model_name='operationalprocedure', index=models.Index(fields=['executor_norm'], name='quality_op__exec_idx')),
        migrations.AddIndex(model_name='operationalprocedure', index=models.Index(fields=['school','academic_year'], name='quality_op__year_idx')),

        migrations.CreateModel(
            name='ProcedureEvidence',
            fields=[
                ('id',          models.UUIDField(default=quality.models._uuid, editable=False, primary_key=True, serialize=False)),
                ('title',       models.CharField(max_length=200, verbose_name='عنوان الدليل')),
                ('description', models.TextField(blank=True)),
                ('file',        models.FileField(blank=True, null=True, upload_to='evidence/%Y/%m/')),
                ('created_at',  models.DateTimeField(auto_now_add=True)),
                ('procedure',   models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='evidences', to='quality.operationalprocedure')),
                ('uploaded_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='uploaded_evidences', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'دليل', 'verbose_name_plural': 'الأدلة', 'ordering': ['-created_at']},
        ),

        migrations.CreateModel(
            name='QualityCommitteeMember',
            fields=[
                ('id',            models.UUIDField(default=quality.models._uuid, editable=False, primary_key=True, serialize=False)),
                ('job_title',     models.CharField(max_length=100, verbose_name='المسمى الوظيفي')),
                ('responsibility',models.CharField(choices=[('رئيس اللجنة','رئيس اللجنة'),('نائب رئيس اللجنة','نائب رئيس اللجنة'),('مقرر','مقرر'),('عضو','عضو')], max_length=30, verbose_name='المسؤولية')),
                ('academic_year', models.CharField(default='2025-2026', max_length=9)),
                ('is_active',     models.BooleanField(default=True)),
                ('domain',  models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='committee_members', to='quality.operationaldomain', verbose_name='المجال المسؤول عنه')),
                ('school',  models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='quality_members', to='core.school')),
                ('user',    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='quality_memberships', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'عضو لجنة جودة', 'verbose_name_plural': 'أعضاء لجنة الجودة', 'ordering': ['responsibility', 'job_title']},
        ),
    ]
