"""
core/migrations/0008_remove_moved_models.py
إزالة النماذج المنقولة من state core — الجداول تبقى كما هي في DB

SeparateDatabaseAndState:
  state_operations  → يحذف النماذج من state Django
  database_operations → لا شيء (الجداول لا تُحذف)
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core',      '0007_add_security_and_consent_fields'),
        ('clinic',    '0001_initial'),
        ('behavior',  '0001_initial'),
        ('transport', '0001_initial'),
        ('library',   '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name='HealthRecord'),
                migrations.DeleteModel(name='ClinicVisit'),
                migrations.DeleteModel(name='BehaviorInfraction'),
                migrations.DeleteModel(name='BehaviorPointRecovery'),
                migrations.DeleteModel(name='SchoolBus'),
                migrations.DeleteModel(name='BusRoute'),
                migrations.DeleteModel(name='LibraryBook'),
                migrations.DeleteModel(name='BookBorrowing'),
                migrations.DeleteModel(name='LibraryActivity'),
            ],
            database_operations=[],  # لا تحذف أي جداول
        ),
    ]
