from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_phase2_schedule_substitute"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ParentStudentLink",
            fields=[
                ("id",           models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("relationship", models.CharField(
                    max_length=20,
                    choices=[("father","الأب"),("mother","الأم"),("guardian","الوصي"),("other","أخرى")],
                    default="father",
                    verbose_name="صلة القرابة",
                )),
                ("is_primary",            models.BooleanField(default=True,  verbose_name="ولي الأمر الأساسي")),
                ("can_view_grades",       models.BooleanField(default=True,  verbose_name="يرى الدرجات")),
                ("can_view_attendance",   models.BooleanField(default=True,  verbose_name="يرى الغياب")),
                ("created_at",            models.DateTimeField(auto_now_add=True)),
                ("school",   models.ForeignKey("core.School",             on_delete=django.db.models.deletion.CASCADE, related_name="parent_links")),
                ("parent",   models.ForeignKey(settings.AUTH_USER_MODEL,  on_delete=django.db.models.deletion.CASCADE, related_name="children_links",  verbose_name="ولي الأمر")),
                ("student",  models.ForeignKey(settings.AUTH_USER_MODEL,  on_delete=django.db.models.deletion.CASCADE, related_name="parent_links",    verbose_name="الطالب")),
            ],
            options={
                "verbose_name":        "ربط ولي أمر",
                "verbose_name_plural": "ربط أولياء الأمور",
                "ordering":            ["student__full_name"],
            },
        ),
        migrations.AddConstraint(
            model_name="parentstudentlink",
            constraint=models.UniqueConstraint(
                fields=["parent", "student", "school"],
                name="unique_parent_student_school",
            ),
        ),
    ]
