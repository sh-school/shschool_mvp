"""exam_control initial migration"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion, uuid


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ('core', '0008_remove_moved_models'),
        ('behavior', '0002_violationcategory_abcd'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel('ExamSession', fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
            ('name', models.CharField(max_length=200)),
            ('session_type', models.CharField(max_length=10, choices=[('mid','منتصف الفصل'),('final','نهاية الفصل'),('makeup','الدور الثاني')], default='final')),
            ('academic_year', models.CharField(max_length=20, default='2025-2026')),
            ('start_date', models.DateField()),
            ('end_date', models.DateField()),
            ('status', models.CharField(max_length=15, choices=[('planned','مُخطَّطة'),('active','جارية'),('completed','منتهية')], default='planned')),
            ('notes', models.TextField(blank=True)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='exam_sessions', to='core.school')),
            ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_exam_sessions', to=settings.AUTH_USER_MODEL)),
        ], options={'ordering': ['-start_date']}),
        migrations.CreateModel('ExamRoom', fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
            ('name', models.CharField(max_length=100)),
            ('capacity', models.PositiveSmallIntegerField(default=30)),
            ('floor', models.CharField(max_length=20, blank=True)),
            ('notes', models.TextField(blank=True)),
            ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rooms', to='exam_control.examsession')),
        ], options={'ordering': ['name']}),
        migrations.CreateModel('ExamSupervisor', fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
            ('role', models.CharField(max_length=15, default='supervisor')),
            ('assigned_at', models.DateTimeField(auto_now_add=True)),
            ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='supervisors', to='exam_control.examsession')),
            ('room', models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name='supervisors', to='exam_control.examroom')),
            ('staff', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='exam_roles', to=settings.AUTH_USER_MODEL)),
        ], options={'unique_together': {('session','staff')}}),
        migrations.CreateModel('ExamSchedule', fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
            ('subject', models.CharField(max_length=100)),
            ('grade_level', models.CharField(max_length=20)),
            ('exam_date', models.DateField()),
            ('start_time', models.TimeField()),
            ('end_time', models.TimeField()),
            ('students_count', models.PositiveSmallIntegerField(default=0)),
            ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='schedules', to='exam_control.examsession')),
            ('room', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='schedules', to='exam_control.examroom')),
        ], options={'ordering': ['exam_date','start_time']}),
        migrations.CreateModel('ExamIncident', fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
            ('incident_type', models.CharField(max_length=15, default='other')),
            ('severity', models.PositiveSmallIntegerField(default=1)),
            ('description', models.TextField()),
            ('injuries', models.TextField(blank=True)),
            ('action_taken', models.TextField(blank=True)),
            ('attachments', models.TextField(blank=True)),
            ('recommendations', models.TextField(blank=True)),
            ('status', models.CharField(max_length=10, default='open')),
            ('incident_time', models.DateTimeField(auto_now_add=True)),
            ('resolved_at', models.DateTimeField(null=True, blank=True)),
            ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='incidents', to='exam_control.examsession')),
            ('room', models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name='incidents', to='exam_control.examroom')),
            ('student', models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name='exam_incidents', to=settings.AUTH_USER_MODEL)),
            ('reported_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reported_exam_incidents', to=settings.AUTH_USER_MODEL)),
            ('behavior_link', models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name='exam_incidents', to='behavior.behaviorinfraction')),
        ], options={'ordering': ['-incident_time']}),
        migrations.CreateModel('ExamEnvelope', fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
            ('action', models.CharField(max_length=15)),
            ('copies', models.PositiveSmallIntegerField(default=0)),
            ('notes', models.TextField(blank=True)),
            ('timestamp', models.DateTimeField(auto_now_add=True)),
            ('schedule', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='envelopes', to='exam_control.examschedule')),
            ('done_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ('witness', models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name='witnessed_envelopes', to=settings.AUTH_USER_MODEL)),
        ], options={'ordering': ['timestamp']}),
        migrations.CreateModel('ExamGradeSheet', fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
            ('papers_count', models.PositiveSmallIntegerField(default=0)),
            ('status', models.CharField(max_length=12, default='pending')),
            ('submitted_at', models.DateTimeField(null=True, blank=True)),
            ('notes', models.TextField(blank=True)),
            ('schedule', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='grade_sheets', to='exam_control.examschedule')),
            ('grader', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='grade_sheets', to=settings.AUTH_USER_MODEL)),
        ]),
    ]
