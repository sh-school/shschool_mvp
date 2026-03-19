"""
assessments/migrations/0002_qatar_grading_fix.py
تصحيح نظام الدرجات ليتوافق مع سياسة وزارة التعليم القطرية:
  - إضافة semester_max_grade لـ AssessmentPackage
  - تعديل StudentSubjectResult: p*_weighted → p*_score + semester_max
  - إضافة AnnualSubjectResult (النتيجة السنوية)
"""
import assessments.models
import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assessments', '0001_initial'),
        ('core', '0001_phase2_schedule_substitute'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [

        # 1. إضافة semester_max_grade لـ AssessmentPackage
        migrations.AddField(
            model_name='assessmentpackage',
            name='semester_max_grade',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('40'), max_digits=5,
                verbose_name='الدرجة القصوى للفصل من المجموع السنوي'
            ),
        ),

        # 2. تحديث AssessmentPackage.weight max_digits
        migrations.AlterField(
            model_name='assessmentpackage',
            name='weight',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('25'), max_digits=6,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(100)
                ],
                verbose_name='وزن الباقة من مجموع الفصل %'
            ),
        ),

        # 3. تحديث Assessment.max_grade default → 10
        migrations.AlterField(
            model_name='assessment',
            name='max_grade',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('10'), max_digits=5,
                verbose_name='الدرجة القصوى الخام'
            ),
        ),

        # 4. تحديث Assessment.weight_in_package max_digits
        migrations.AlterField(
            model_name='assessment',
            name='weight_in_package',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('100'), max_digits=6,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(100)
                ],
                verbose_name='وزنه داخل الباقة %'
            ),
        ),

        # 5. إضافة نوع المشاركة الصفية
        migrations.AlterField(
            model_name='assessment',
            name='assessment_type',
            field=models.CharField(
                choices=[
                    ('exam','اختبار'), ('quiz','اختبار قصير'), ('homework','واجب'),
                    ('project','مشروع'), ('classwork','عمل صفي'), ('oral','شفهي'),
                    ('practical','عملي'), ('participation','مشاركة صفية'),
                ],
                default='exam', max_length=15
            ),
        ),

        # 6. تحديث StudentSubjectResult: إزالة الحقول القديمة وإضافة الجديدة
        migrations.RenameField(
            model_name='studentsubjectresult',
            old_name='p1_weighted',
            new_name='p1_score',
        ),
        migrations.RenameField(
            model_name='studentsubjectresult',
            old_name='p2_weighted',
            new_name='p2_score',
        ),
        migrations.RenameField(
            model_name='studentsubjectresult',
            old_name='p3_weighted',
            new_name='p3_score',
        ),
        migrations.RenameField(
            model_name='studentsubjectresult',
            old_name='p4_weighted',
            new_name='p4_score',
        ),
        migrations.AddField(
            model_name='studentsubjectresult',
            name='semester_max',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('40'), max_digits=5,
                verbose_name='الدرجة القصوى للفصل'
            ),
        ),
        migrations.RemoveField(
            model_name='studentsubjectresult',
            name='status',
        ),
        migrations.RemoveField(
            model_name='studentsubjectresult',
            name='pass_grade',
        ),

        # 7. إنشاء AnnualSubjectResult
        migrations.CreateModel(
            name='AnnualSubjectResult',
            fields=[
                ('id',            models.UUIDField(default=assessments.models._uuid, editable=False, primary_key=True, serialize=False)),
                ('academic_year', models.CharField(default='2025-2026', max_length=9)),
                ('s1_total',      models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, verbose_name='مجموع الفصل الأول (من 40)')),
                ('s2_total',      models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, verbose_name='مجموع الفصل الثاني (من 60)')),
                ('annual_total',  models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, verbose_name='المجموع السنوي (من 100)')),
                ('pass_grade',    models.DecimalField(decimal_places=2, default=Decimal('50'), max_digits=5, verbose_name='درجة النجاح')),
                ('status',        models.CharField(
                    choices=[('pass','ناجح'),('fail','راسب'),('incomplete','غير مكتمل'),('second_round','دور ثانٍ')],
                    db_index=True, default='incomplete', max_length=12
                )),
                ('updated_at',    models.DateTimeField(auto_now=True)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='annual_results', to=settings.AUTH_USER_MODEL)),
                ('setup',   models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='annual_results', to='assessments.subjectclasssetup')),
                ('school',  models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='annual_results', to='core.school')),
            ],
            options={'verbose_name': 'نتيجة سنوية', 'verbose_name_plural': 'النتائج السنوية'},
        ),
        migrations.AddIndex(
            model_name='annualsubjectresult',
            index=models.Index(fields=['student','school','academic_year'], name='annual_result_student_idx'),
        ),
        migrations.AddIndex(
            model_name='annualsubjectresult',
            index=models.Index(fields=['status','school','academic_year'], name='annual_result_status_idx'),
        ),
        migrations.AddConstraint(
            model_name='annualsubjectresult',
            constraint=models.UniqueConstraint(
                fields=['student','setup','academic_year'],
                name='unique_annual_result'
            ),
        ),
    ]
