"""
Migration 0001 — operations app
يشمل: المرحلة 0 + 1 + 2
"""
import django.db.models.deletion
import operations.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('core', '0001_phase2_schedule_substitute'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [

        # ── المرحلة 0+1: المواد والحصص والحضور ──────────────

        migrations.CreateModel(
            name='Subject',
            fields=[
                ('id',      models.UUIDField(default=operations.models._uuid, editable=False, primary_key=True, serialize=False)),
                ('name_ar', models.CharField(max_length=100, verbose_name='اسم المادة')),
                ('code',    models.CharField(blank=True, max_length=20)),
                ('school',  models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subjects', to='core.school')),
            ],
            options={'verbose_name': 'مادة دراسية', 'verbose_name_plural': 'المواد الدراسية', 'ordering': ['name_ar']},
        ),

        migrations.CreateModel(
            name='Session',
            fields=[
                ('id',         models.UUIDField(default=operations.models._uuid, editable=False, primary_key=True, serialize=False)),
                ('date',       models.DateField(db_index=True, verbose_name='التاريخ')),
                ('start_time', models.TimeField(verbose_name='وقت البدء')),
                ('end_time',   models.TimeField(verbose_name='وقت النهاية')),
                ('status',     models.CharField(choices=[('scheduled','مجدولة'),('in_progress','جارية'),('completed','مكتملة'),('cancelled','ملغاة')], db_index=True, default='scheduled', max_length=15)),
                ('notes',      models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('class_group',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sessions', to='core.classgroup')),
                ('school',     models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sessions', to='core.school')),
                ('teacher',    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sessions', to=settings.AUTH_USER_MODEL, verbose_name='المعلم')),
                ('subject',    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sessions', to='operations.subject')),
            ],
            options={'verbose_name': 'حصة', 'verbose_name_plural': 'الحصص'},
        ),
        migrations.AddIndex(model_name='session', index=models.Index(fields=['school', 'date'], name='operations__school__dbde3d_idx')),
        migrations.AddIndex(model_name='session', index=models.Index(fields=['teacher', 'date'], name='operations__teacher_e83ebc_idx')),
        migrations.AddIndex(model_name='session', index=models.Index(fields=['class_group', 'date'], name='operations__class_g_c6792c_idx')),
        migrations.AddConstraint(model_name='session', constraint=models.UniqueConstraint(fields=('teacher','date','start_time'), name='no_teacher_time_overlap')),
        migrations.AddConstraint(model_name='session', constraint=models.UniqueConstraint(fields=('class_group','date','start_time'), name='no_class_time_overlap')),

        migrations.CreateModel(
            name='StudentAttendance',
            fields=[
                ('id',           models.UUIDField(default=operations.models._uuid, editable=False, primary_key=True, serialize=False)),
                ('status',       models.CharField(choices=[('present','حاضر'),('absent','غائب'),('late','متأخر'),('excused','معذور')], db_index=True, default='present', max_length=10)),
                ('excuse_type',  models.CharField(blank=True, choices=[('medical','طبي'),('family','ظروف عائلية'),('official','رسمي'),('other','أخرى')], max_length=20)),
                ('excuse_notes', models.TextField(blank=True)),
                ('marked_at',    models.DateTimeField(auto_now_add=True)),
                ('updated_at',   models.DateTimeField(auto_now=True)),
                ('marked_by',    models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='marked_attendances', to=settings.AUTH_USER_MODEL)),
                ('school',       models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attendances', to='core.school')),
                ('session',      models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attendances', to='operations.session')),
                ('student',      models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attendances', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'حضور طالب', 'verbose_name_plural': 'سجلات الحضور',
                'indexes': [
                    models.Index(fields=['school','session'], name='operations__school__1e3454_idx'),
                    models.Index(fields=['student','status'], name='operations__student_8be0ff_idx'),
                    models.Index(fields=['student','status','marked_at'], name='operations__student_c48689_idx'),
                ],
                'constraints': [models.UniqueConstraint(fields=('session','student'), name='unique_attendance_per_session')],
            },
        ),

        migrations.CreateModel(
            name='AbsenceAlert',
            fields=[
                ('id',            models.UUIDField(default=operations.models._uuid, editable=False, primary_key=True, serialize=False)),
                ('absence_count', models.IntegerField()),
                ('period_start',  models.DateField()),
                ('period_end',    models.DateField()),
                ('status',        models.CharField(choices=[('pending','قيد المراجعة'),('notified','تم الإبلاغ'),('resolved','تم الحل')], db_index=True, default='pending', max_length=10)),
                ('created_at',    models.DateTimeField(auto_now_add=True, db_index=True)),
                ('resolved_by',   models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='resolved_alerts', to=settings.AUTH_USER_MODEL)),
                ('school',        models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.school')),
                ('student',       models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='absence_alerts', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'تنبيه غياب', 'verbose_name_plural': 'تنبيهات الغياب', 'ordering': ['-created_at']},
        ),

        # ── المرحلة 2: الجداول الذكية + نظام البديل ──────────

        migrations.CreateModel(
            name='ScheduleSlot',
            fields=[
                ('id',            models.UUIDField(default=operations.models._uuid, editable=False, primary_key=True, serialize=False)),
                ('day_of_week',   models.IntegerField(choices=[(0,'الأحد'),(1,'الاثنين'),(2,'الثلاثاء'),(3,'الأربعاء'),(4,'الخميس')], verbose_name='اليوم')),
                ('period_number', models.IntegerField(verbose_name='رقم الحصة')),
                ('start_time',    models.TimeField(verbose_name='وقت البدء')),
                ('end_time',      models.TimeField(verbose_name='وقت النهاية')),
                ('academic_year', models.CharField(default='2025-2026', max_length=9)),
                ('is_active',     models.BooleanField(default=True)),
                ('created_at',    models.DateTimeField(auto_now_add=True)),
                ('school',        models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='schedule_slots', to='core.school')),
                ('teacher',       models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='schedule_slots', to=settings.AUTH_USER_MODEL)),
                ('class_group',   models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='schedule_slots', to='core.classgroup')),
                ('subject',       models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='schedule_slots', to='operations.subject')),
            ],
            options={'verbose_name': 'حصة جدول', 'verbose_name_plural': 'جدول الحصص', 'ordering': ['day_of_week','period_number']},
        ),
        migrations.AddConstraint(model_name='scheduleslot', constraint=models.UniqueConstraint(condition=models.Q(is_active=True), fields=['teacher','day_of_week','period_number','academic_year'], name='no_teacher_period_overlap')),
        migrations.AddConstraint(model_name='scheduleslot', constraint=models.UniqueConstraint(condition=models.Q(is_active=True), fields=['class_group','day_of_week','period_number','academic_year'], name='no_class_period_overlap')),

        migrations.CreateModel(
            name='TeacherAbsence',
            fields=[
                ('id',           models.UUIDField(default=operations.models._uuid, editable=False, primary_key=True, serialize=False)),
                ('date',         models.DateField(db_index=True, verbose_name='تاريخ الغياب')),
                ('reason',       models.CharField(choices=[('sick','إجازة مرضية'),('official','مهمة رسمية'),('emergency','ظرف طارئ'),('training','تدريب'),('other','أخرى')], default='other', max_length=20)),
                ('reason_notes', models.TextField(blank=True, verbose_name='تفاصيل')),
                ('status',       models.CharField(choices=[('pending','بانتظار البديل'),('covered','مغطّى'),('uncovered','غير مغطّى')], db_index=True, default='pending', max_length=10)),
                ('created_at',   models.DateTimeField(auto_now_add=True)),
                ('school',       models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='teacher_absences', to='core.school')),
                ('teacher',      models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='absences_as_teacher', to=settings.AUTH_USER_MODEL)),
                ('reported_by',  models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reported_absences', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'غياب معلم', 'verbose_name_plural': 'غيابات المعلمين', 'ordering': ['-date']},
        ),
        migrations.AddConstraint(model_name='teacherabsence', constraint=models.UniqueConstraint(fields=['teacher','date'], name='one_absence_per_teacher_day')),

        migrations.CreateModel(
            name='SubstituteAssignment',
            fields=[
                ('id',          models.UUIDField(default=operations.models._uuid, editable=False, primary_key=True, serialize=False)),
                ('status',      models.CharField(choices=[('assigned','مُعيَّن'),('confirmed','قبِل'),('declined','رفض')], default='assigned', max_length=10)),
                ('notes',       models.TextField(blank=True)),
                ('created_at',  models.DateTimeField(auto_now_add=True)),
                ('absence',     models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assignments', to='operations.teacherabsence')),
                ('slot',        models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='substitute_assignments', to='operations.scheduleslot')),
                ('substitute',  models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='substitute_assignments', to=settings.AUTH_USER_MODEL)),
                ('school',      models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='substitute_assignments', to='core.school')),
                ('assigned_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_assignments', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'تعيين بديل', 'verbose_name_plural': 'تعيينات البدلاء', 'ordering': ['-created_at']},
        ),
        migrations.AddConstraint(model_name='substituteassignment', constraint=models.UniqueConstraint(fields=['slot','absence'], name='one_substitute_per_slot_absence')),
    ]
