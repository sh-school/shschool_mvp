"""
assessments/migrations/0001_initial.py
المرحلة 3 — التقييمات والاختبارات (الباقات الأربع)
"""
import assessments.models
import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('core', '0001_phase2_schedule_substitute'),
        ('operations', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [

        migrations.CreateModel(
            name='SubjectClassSetup',
            fields=[
                ('id',            models.UUIDField(default=assessments.models._uuid, editable=False, primary_key=True, serialize=False)),
                ('academic_year', models.CharField(default='2025-2026', max_length=9)),
                ('is_active',     models.BooleanField(default=True)),
                ('school',        models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subject_setups', to='core.school')),
                ('subject',       models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='class_setups', to='operations.subject')),
                ('class_group',   models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subject_setups', to='core.classgroup')),
                ('teacher',       models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subject_setups', to=settings.AUTH_USER_MODEL, verbose_name='المعلم المسؤول')),
            ],
            options={'verbose_name': 'إعداد مادة', 'verbose_name_plural': 'إعدادات المواد'},
        ),
        migrations.AddConstraint(
            model_name='subjectclasssetup',
            constraint=models.UniqueConstraint(
                condition=models.Q(is_active=True),
                fields=['subject', 'class_group', 'academic_year'],
                name='unique_subject_class_year',
            ),
        ),

        migrations.CreateModel(
            name='AssessmentPackage',
            fields=[
                ('id',           models.UUIDField(default=assessments.models._uuid, editable=False, primary_key=True, serialize=False)),
                ('package_type', models.CharField(choices=[('P1','الباقة الأولى — أعمال مدرسية'),('P2','الباقة الثانية — اختبارات قصيرة'),('P3','الباقة الثالثة — اختبار نصفي'),('P4','الباقة الرابعة — اختبار نهائي')], max_length=2, verbose_name='نوع الباقة')),
                ('semester',     models.CharField(choices=[('S1','الفصل الأول'),('S2','الفصل الثاني')], default='S1', max_length=2)),
                ('max_grade',    models.DecimalField(decimal_places=2, default=Decimal('100'), max_digits=5, verbose_name='الدرجة القصوى')),
                ('weight',       models.DecimalField(decimal_places=2, default=Decimal('25'), max_digits=5, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)], verbose_name='الوزن النسبي %')),
                ('is_active',    models.BooleanField(default=True)),
                ('created_at',   models.DateTimeField(auto_now_add=True)),
                ('setup',        models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='packages', to='assessments.subjectclasssetup')),
                ('school',       models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='packages', to='core.school')),
            ],
            options={'verbose_name': 'باقة تقييم', 'verbose_name_plural': 'باقات التقييم', 'ordering': ['semester', 'package_type']},
        ),
        migrations.AddConstraint(
            model_name='assessmentpackage',
            constraint=models.UniqueConstraint(
                fields=['setup', 'package_type', 'semester'],
                name='unique_package_per_setup_semester',
            ),
        ),

        migrations.CreateModel(
            name='Assessment',
            fields=[
                ('id',                models.UUIDField(default=assessments.models._uuid, editable=False, primary_key=True, serialize=False)),
                ('title',             models.CharField(max_length=200, verbose_name='عنوان التقييم')),
                ('assessment_type',   models.CharField(choices=[('exam','اختبار'),('quiz','اختبار قصير'),('homework','واجب'),('project','مشروع'),('classwork','عمل صفي'),('oral','شفهي'),('practical','عملي')], default='exam', max_length=15)),
                ('date',              models.DateField(blank=True, null=True, verbose_name='تاريخ التقييم')),
                ('max_grade',         models.DecimalField(decimal_places=2, default=Decimal('100'), max_digits=5, verbose_name='الدرجة القصوى')),
                ('weight_in_package', models.DecimalField(decimal_places=2, default=Decimal('100'), max_digits=5, verbose_name='وزنه داخل الباقة %')),
                ('status',            models.CharField(choices=[('draft','مسودة'),('published','منشور'),('graded','مصحَّح'),('closed','مغلق')], db_index=True, default='draft', max_length=10)),
                ('description',       models.TextField(blank=True, verbose_name='وصف / تعليمات')),
                ('created_at',        models.DateTimeField(auto_now_add=True)),
                ('package',     models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assessments', to='assessments.assessmentpackage')),
                ('school',      models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assessments', to='core.school')),
                ('created_by',  models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_assessments', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'تقييم', 'verbose_name_plural': 'التقييمات', 'ordering': ['date', 'package__package_type']},
        ),

        migrations.CreateModel(
            name='StudentAssessmentGrade',
            fields=[
                ('id',         models.UUIDField(default=assessments.models._uuid, editable=False, primary_key=True, serialize=False)),
                ('grade',      models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, validators=[django.core.validators.MinValueValidator(0)], verbose_name='الدرجة')),
                ('is_absent',  models.BooleanField(default=False, verbose_name='غائب')),
                ('is_excused', models.BooleanField(default=False, verbose_name='معذور')),
                ('notes',      models.CharField(blank=True, max_length=200, verbose_name='ملاحظة')),
                ('entered_at', models.DateTimeField(auto_now=True)),
                ('assessment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='grades', to='assessments.assessment')),
                ('student',    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assessment_grades', to=settings.AUTH_USER_MODEL)),
                ('school',     models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='student_grades', to='core.school')),
                ('entered_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='entered_grades', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'درجة طالب', 'verbose_name_plural': 'درجات الطلاب'},
        ),
        migrations.AddIndex(model_name='studentassessmentgrade', index=models.Index(fields=['student','school'], name='assess_grade_student_idx')),
        migrations.AddIndex(model_name='studentassessmentgrade', index=models.Index(fields=['assessment','school'], name='assess_grade_assess_idx')),
        migrations.AddConstraint(
            model_name='studentassessmentgrade',
            constraint=models.UniqueConstraint(fields=['assessment','student'], name='unique_grade_per_student_assessment'),
        ),

        migrations.CreateModel(
            name='StudentSubjectResult',
            fields=[
                ('id',          models.UUIDField(default=assessments.models._uuid, editable=False, primary_key=True, serialize=False)),
                ('semester',    models.CharField(choices=[('S1','الفصل الأول'),('S2','الفصل الثاني')], default='S1', max_length=2)),
                ('p1_weighted', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, verbose_name='الباقة 1')),
                ('p2_weighted', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, verbose_name='الباقة 2')),
                ('p3_weighted', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, verbose_name='الباقة 3')),
                ('p4_weighted', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, verbose_name='الباقة 4')),
                ('total',       models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, verbose_name='المجموع')),
                ('status',      models.CharField(choices=[('pass','ناجح'),('fail','راسب'),('pending','قيد الرصد')], db_index=True, default='pending', max_length=10)),
                ('pass_grade',  models.DecimalField(decimal_places=2, default=Decimal('50'), max_digits=5, verbose_name='درجة النجاح')),
                ('updated_at',  models.DateTimeField(auto_now=True)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subject_results', to=settings.AUTH_USER_MODEL)),
                ('setup',   models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='student_results', to='assessments.subjectclasssetup')),
                ('school',  models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subject_results', to='core.school')),
            ],
            options={'verbose_name': 'نتيجة مادة', 'verbose_name_plural': 'نتائج المواد'},
        ),
        migrations.AddIndex(model_name='studentsubjectresult', index=models.Index(fields=['student','school','semester'], name='assess_result_student_idx')),
        migrations.AddIndex(model_name='studentsubjectresult', index=models.Index(fields=['setup','semester'], name='assess_result_setup_idx')),
        migrations.AddConstraint(
            model_name='studentsubjectresult',
            constraint=models.UniqueConstraint(fields=['student','setup','semester'], name='unique_result_per_student_setup_semester'),
        ),
    ]
