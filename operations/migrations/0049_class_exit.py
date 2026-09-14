"""خروجُ الطالب من الفصل بإذن المعلّم — ومعه عزلُ المدرسة (كما في 0047)."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import operations.models

TABLE = "operations_classexit"
PREDICATE = f"{TABLE}.school_id = public.app_rls_school()"
ENABLE = f"""
ALTER TABLE public.{TABLE} ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS school_isolation ON public.{TABLE};
CREATE POLICY school_isolation ON public.{TABLE} USING ({PREDICATE}) WITH CHECK ({PREDICATE});
"""
DISABLE = f"""
DROP POLICY IF EXISTS school_isolation ON public.{TABLE};
ALTER TABLE public.{TABLE} DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0065_role_support_companion"),
        ("operations", "0048_teacher_late_source"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ClassExit",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=operations.models._uuid,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "destination",
                    models.CharField(
                        choices=[
                            ("clinic", "العيادة"),
                            ("admin", "الإدارة / المشرف"),
                            ("restroom", "دورة المياه"),
                            ("other", "أخرى"),
                        ],
                        default="restroom",
                        max_length=10,
                    ),
                ),
                ("left_at", models.DateTimeField(verbose_name="وقتُ الخروج")),
                (
                    "returned_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="وقتُ العودة"),
                ),
                (
                    "allowed_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="class_exits_allowed",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="class_exits",
                        to="core.school",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="class_exits",
                        to="operations.session",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="class_exits",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "خروجٌ من الفصل",
                "verbose_name_plural": "خروجٌ من الفصل",
                "ordering": ["-left_at"],
                "indexes": [
                    models.Index(
                        fields=["school", "session"], name="operations__school__451f3e_idx"
                    ),
                    models.Index(
                        fields=["student", "left_at"], name="operations__student_0f298f_idx"
                    ),
                ],
            },
        ),
        migrations.RunSQL(sql=ENABLE, reverse_sql=DISABLE),
    ]
