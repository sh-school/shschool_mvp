"""
Migration: إضافة جدول ربط المنفذين بالمستخدمين
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("quality", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0001_phase2_schedule_substitute"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExecutorMapping",
            fields=[
                ("id",            models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("executor_norm", models.CharField(max_length=100, verbose_name="المسمى الوظيفي (نص)", db_index=True)),
                ("academic_year", models.CharField(max_length=9, default="2025-2026")),
                ("school",        models.ForeignKey("core.School",      on_delete=django.db.models.deletion.CASCADE, related_name="executor_mappings")),
                ("user",          models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.SET_NULL, null=True, blank=True, related_name="executor_mappings", verbose_name="الموظف")),
                ("created_at",    models.DateTimeField(auto_now_add=True)),
                ("updated_at",    models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name":        "ربط منفذ",
                "verbose_name_plural": "ربط المنفذين",
                "ordering":            ["executor_norm"],
            },
        ),
        migrations.AddConstraint(
            model_name="executormapping",
            constraint=models.UniqueConstraint(
                fields=["school", "executor_norm", "academic_year"],
                name="unique_executor_mapping_per_school_year",
            ),
        ),
    ]
