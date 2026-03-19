from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


def _uuid():
    return uuid.uuid4()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_behaviorinfraction_created_at'),
    ]

    operations = [
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('action', models.CharField(choices=[('create','إنشاء'),('update','تعديل'),('delete','حذف'),('view','عرض'),('export','تصدير'),('login','تسجيل دخول'),('logout','تسجيل خروج')], max_length=10)),
                ('model_name', models.CharField(choices=[('HealthRecord','سجل صحي'),('BehaviorInfraction','مخالفة سلوكية'),('StudentSubjectResult','درجة طالب'),('ClinicVisit','زيارة عيادة'),('CustomUser','مستخدم'),('ParentStudentLink','ربط ولي أمر'),('BookBorrowing','إعارة كتاب'),('other','أخرى')], default='other', max_length=50)),
                ('object_id', models.CharField(blank=True, max_length=100)),
                ('object_repr', models.CharField(blank=True, max_length=300, verbose_name='وصف السجل')),
                ('changes', models.JSONField(blank=True, null=True, verbose_name='التغييرات')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.CharField(blank=True, max_length=300)),
                ('timestamp', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('school', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='audit_logs', to='core.school')),
                ('user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='audit_actions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'سجل مراجعة',
                'verbose_name_plural': 'سجلات المراجعة',
                'ordering': ['-timestamp'],
            },
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['school', 'timestamp'], name='auditlog_school_ts_idx'),
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['model_name', 'object_id'], name='auditlog_model_obj_idx'),
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['user', 'timestamp'], name='auditlog_user_ts_idx'),
        ),
        migrations.CreateModel(
            name='ConsentRecord',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('data_type', models.CharField(choices=[('health','البيانات الصحية'),('behavior','بيانات السلوك'),('grades','الدرجات والتقييمات'),('attendance','الحضور والغياب'),('transport','بيانات النقل'),('photo','الصور والمرئيات'),('all','جميع البيانات')], max_length=20)),
                ('is_given', models.BooleanField(default=True, verbose_name='تمت الموافقة')),
                ('method', models.CharField(choices=[('form','استمارة ورقية'),('digital','موافقة رقمية'),('verbal','موافقة شفهية موثقة')], default='digital', max_length=10)),
                ('given_at', models.DateTimeField(auto_now_add=True)),
                ('withdrawn_at', models.DateTimeField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('parent', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='consent_records', to=settings.AUTH_USER_MODEL)),
                ('recorded_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='consents_recorded', to=settings.AUTH_USER_MODEL)),
                ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.school')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='consent_as_student', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'سجل موافقة',
                'verbose_name_plural': 'سجلات الموافقة',
                'ordering': ['-given_at'],
                'unique_together': {('parent', 'student', 'data_type')},
            },
        ),
    ]
