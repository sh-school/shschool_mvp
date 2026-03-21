"""
Migration: 0003_operations_search_indexes
Indexes على جداول العمليات (الحصص، الحضور).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0002_alter_scheduleslot_subject"),
    ]

    operations = [
        # ── Session indexes ────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="session",
            index=models.Index(
                fields=["date"],
                name="session_date_btree_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="session",
            index=models.Index(
                fields=["teacher", "date"],
                name="session_teacher_date_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="session",
            index=models.Index(
                fields=["class_group", "date"],
                name="session_class_date_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="session",
            index=models.Index(
                fields=["status"],
                name="session_status_btree_idx",
            ),
        ),

        # ── StudentAttendance indexes ──────────────────────────────────────
        migrations.AddIndex(
            model_name="studentattendance",
            index=models.Index(
                fields=["student", "status"],
                name="attendance_student_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="studentattendance",
            index=models.Index(
                fields=["session", "status"],
                name="attendance_session_status_idx",
            ),
        ),
    ]
