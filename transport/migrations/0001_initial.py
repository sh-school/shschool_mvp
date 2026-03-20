"""
transport/migrations/0001_initial.py
نقل SchoolBus و BusRoute من core إلى transport
"""
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('core', '0007_add_security_and_consent_fields'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='SchoolBus',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('bus_number', models.CharField(max_length=20, verbose_name='رقم الحافلة')),
                        ('driver_name', models.CharField(max_length=200, verbose_name='اسم السائق')),
                        ('driver_phone', models.CharField(max_length=20, verbose_name='جوال السائق')),
                        ('capacity', models.PositiveIntegerField(default=30)),
                        ('karwa_id', models.CharField(blank=True, max_length=50, verbose_name='رقم كروة (Karwa ID)')),
                        ('gps_link', models.URLField(blank=True, verbose_name='رابط التتبع (GPS)')),
                        ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='buses', to='core.school')),
                        ('supervisor', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='supervised_buses', to='core.customuser', verbose_name='مشرف الباص')),
                    ],
                    options={'verbose_name': 'حافلة مدرسية', 'verbose_name_plural': 'الحافلات المدرسية', 'db_table': 'core_schoolbus'},
                ),
                migrations.CreateModel(
                    name='BusRoute',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('area_name', models.CharField(max_length=200, verbose_name='المنطقة')),
                        ('bus', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='routes', to='transport.schoolbus')),
                        ('students', models.ManyToManyField(related_name='bus_routes', to='core.customuser', verbose_name='الطلاب')),
                    ],
                    options={'verbose_name': 'خط سير', 'verbose_name_plural': 'خطوط السير', 'db_table': 'core_busroute'},
                ),
            ],
            database_operations=[],
        ),
    ]
