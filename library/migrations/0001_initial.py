"""
library/migrations/0001_initial.py
نقل LibraryBook و BookBorrowing و LibraryActivity من core إلى library
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
                    name='LibraryBook',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('title', models.CharField(max_length=500, verbose_name='عنوان الكتاب')),
                        ('author', models.CharField(max_length=200, verbose_name='المؤلف')),
                        ('isbn', models.CharField(blank=True, max_length=20, verbose_name='ISBN')),
                        ('category', models.CharField(max_length=100, verbose_name='التصنيف (ديوي العشري)')),
                        ('book_type', models.CharField(choices=[('PRINT','مطبوع'),('DIGITAL','رقمي / PDF'),('PERIODICAL','دورية / مجلة')], default='PRINT', max_length=20)),
                        ('quantity', models.PositiveIntegerField(default=1, verbose_name='الكمية المتوفرة')),
                        ('available_qty', models.PositiveIntegerField(default=1, verbose_name='الكمية المتاحة للإعارة')),
                        ('digital_file', models.FileField(blank=True, null=True, upload_to='library/digital/', verbose_name='الملف الرقمي')),
                        ('location', models.CharField(blank=True, max_length=100, verbose_name='موقع الكتاب (الرف)')),
                        ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='library_books', to='core.school')),
                    ],
                    options={'verbose_name': 'كتاب مكتبة', 'verbose_name_plural': 'كتب المكتبة', 'db_table': 'core_librarybook'},
                ),
                migrations.CreateModel(
                    name='BookBorrowing',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('borrow_date', models.DateField(auto_now_add=True)),
                        ('due_date', models.DateField(verbose_name='تاريخ الإرجاع المتوقع')),
                        ('return_date', models.DateField(blank=True, null=True, verbose_name='تاريخ الإرجاع الفعلي')),
                        ('status', models.CharField(choices=[('BORROWED','قيد الإعارة'),('RETURNED','تم الإرجاع'),('OVERDUE','متأخر'),('LOST','مفقود')], default='BORROWED', max_length=20)),
                        ('book', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='borrowings', to='library.librarybook')),
                        ('librarian', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='processed_borrowings', to='core.customuser', verbose_name='أمين المكتبة')),
                        ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='borrowed_books', to='core.customuser', verbose_name='المستعير')),
                    ],
                    options={'verbose_name': 'عملية إعارة', 'verbose_name_plural': 'عمليات الإعارة', 'ordering': ['-borrow_date', '-id'], 'db_table': 'core_bookborrowing'},
                ),
                migrations.CreateModel(
                    name='LibraryActivity',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('title', models.CharField(max_length=200, verbose_name='اسم النشاط')),
                        ('description', models.TextField(verbose_name='وصف النشاط')),
                        ('date', models.DateField()),
                        ('outcome', models.TextField(blank=True, verbose_name='مخرجات النشاط')),
                        ('participants', models.ManyToManyField(related_name='library_activities', to='core.customuser', verbose_name='المشاركون')),
                        ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.school')),
                    ],
                    options={'verbose_name': 'نشاط مكتبة', 'verbose_name_plural': 'أنشطة المكتبة', 'db_table': 'core_libraryactivity'},
                ),
            ],
            database_operations=[],
        ),
    ]
