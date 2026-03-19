from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("core", "0001_phase2_schedule_substitute"),
    ]

    operations = [
        migrations.CreateModel(
            name="ImportLog",
            fields=[
                ("id",            models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("file_name",     models.CharField(max_length=255)),
                ("status",        models.CharField(
                    choices=[
                        ("pending",    "قيد المعالجة"),
                        ("validating", "جاري التحقق"),
                        ("importing",  "جاري الاستيراد"),
                        ("completed",  "مكتمل"),
                        ("failed",     "فشل"),
                    ],
                    default="pending", max_length=15,
                )),
                ("total_rows",    models.IntegerField(default=0)),
                ("imported_rows", models.IntegerField(default=0)),
                ("failed_rows",   models.IntegerField(default=0)),
                ("error_log",     models.JSONField(blank=True, default=list)),
                ("started_at",    models.DateTimeField(auto_now_add=True)),
                ("completed_at",  models.DateTimeField(blank=True, null=True)),
                ("school",        models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="core.school")),
                ("uploaded_by",   models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to="core.customuser")),
            ],
            options={"ordering": ["-started_at"], "verbose_name": "سجل استيراد"},
        ),
    ]
