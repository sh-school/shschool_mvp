"""
clinic/migrations/0001_initial.py
نقل HealthRecord و ClinicVisit من core إلى clinic
SeparateDatabaseAndState: يُحدّث حالة Django فقط — الجداول موجودة مسبقاً
"""
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('core', '0007_add_security_and_consent_fields'),   # آخر migration في core
    ]

    operations = [
        # SeparateDatabaseAndState:
        # state_operations  → ما يراه Django (ينشئ النموذج في state)
        # database_operations → ما يحدث فعلاً في DB (لا شيء — الجداول موجودة)
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='HealthRecord',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('blood_type', models.CharField(blank=True, choices=[('A+','A+'),('A-','A-'),('B+','B+'),('B-','B-'),('AB+','AB+'),('AB-','AB-'),('O+','O+'),('O-','O-')], max_length=3)),
                        ('allergies', models.TextField(blank=True, verbose_name='الحساسية')),
                        ('chronic_diseases', models.TextField(blank=True, verbose_name='الأمراض المزمنة')),
                        ('medications', models.TextField(blank=True, verbose_name='الأدوية المستمرة')),
                        ('emergency_contact_name', models.CharField(blank=True, max_length=200)),
                        ('emergency_contact_phone', models.CharField(blank=True, max_length=20)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('student', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='health_record', to='core.customuser')),
                    ],
                    options={'verbose_name': 'سجل صحي', 'verbose_name_plural': 'السجلات الصحية', 'db_table': 'core_healthrecord'},
                ),
                migrations.CreateModel(
                    name='ClinicVisit',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('visit_date', models.DateTimeField(auto_now_add=True)),
                        ('reason', models.TextField(verbose_name='سبب الزيارة')),
                        ('symptoms', models.TextField(blank=True, verbose_name='الأعراض')),
                        ('temperature', models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True)),
                        ('treatment', models.TextField(blank=True, verbose_name='الإجراء المتخذ')),
                        ('is_sent_home', models.BooleanField(default=False, verbose_name='تم إرساله للمنزل')),
                        ('parent_notified', models.BooleanField(default=False, verbose_name='تم إبلاغ ولي الأمر')),
                        ('nurse', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='nurse_visits', to='core.customuser')),
                        ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.school')),
                        ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='clinic_visits', to='core.customuser')),
                    ],
                    options={'verbose_name': 'زيارة عيادة', 'verbose_name_plural': 'زيارات العيادة', 'ordering': ['-visit_date'], 'db_table': 'core_clinicvisit'},
                ),
            ],
            database_operations=[],  # الجداول موجودة — لا تعديل على DB
        ),
    ]
