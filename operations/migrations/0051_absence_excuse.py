"""عذرُ الغياب المقبول — قرارٌ واحدٌ بمستنده يغطّي مدّةً، ومعه عزلُ المدرسة (كما في 0049)."""

import core.validators
import django.db.models.deletion
import operations.models
from django.conf import settings
from django.db import migrations, models


TABLE = "operations_absenceexcuse"
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
        ("core", "0066_auditlog_failed_login_actions"),
        ("operations", "0050_teacher_out_source"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="studentattendance",
            name="excuse_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("medical", "مرضٌ بتقريرٍ طبّيّ"),
                    ("bereavement", "وفاةٌ في القرابة الأولى"),
                    ("family", "ظرفٌ عائليٌّ طارئٌ بكتابٍ رسميّ"),
                    ("state_representation", "تمثيلُ الدولة في لقاءٍ خارجيّ"),
                    ("official", "موعدُ محكمةٍ أو هيئةٍ حكوميّة، أو مقابلةٌ للثاني عشر"),
                    ("other", "أخرى (قبل القائمة المغلقة)"),
                ],
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="AbsenceExcuse",
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
                ("date_from", models.DateField(verbose_name="من")),
                ("date_to", models.DateField(verbose_name="إلى")),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("medical", "مرضٌ بتقريرٍ طبّيّ"),
                            ("bereavement", "وفاةٌ في القرابة الأولى"),
                            ("family", "ظرفٌ عائليٌّ طارئٌ بكتابٍ رسميّ"),
                            ("state_representation", "تمثيلُ الدولة في لقاءٍ خارجيّ"),
                            ("official", "موعدُ محكمةٍ أو هيئةٍ حكوميّة، أو مقابلةٌ للثاني عشر"),
                        ],
                        max_length=20,
                        verbose_name="نوعُ العذر",
                    ),
                ),
                ("notes", models.TextField(blank=True, verbose_name="بيان")),
                (
                    "document",
                    models.FileField(
                        blank=True,
                        upload_to=operations.models._excuse_upload_path,
                        validators=[
                            core.validators.FileTypeValidator(
                                allowed_types="excuse", max_size_mb=10
                            )
                        ],
                        verbose_name="المستند",
                    ),
                ),
                ("granted_at", models.DateTimeField(auto_now_add=True)),
                ("after_deadline", models.BooleanField(default=False)),
                (
                    "override_reason",
                    models.TextField(blank=True, verbose_name="سببُ القبول بعد المهلة"),
                ),
                (
                    "granted_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="absence_excuses_granted",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="absence_excuses",
                        to="core.school",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="absence_excuses",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "عذرُ غياب",
                "verbose_name_plural": "أعذارُ الغياب",
                "ordering": ["-date_from"],
            },
        ),
        migrations.AddField(
            model_name="studentattendance",
            name="excuse",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="rows",
                to="operations.absenceexcuse",
                verbose_name="العذرُ المقبول",
            ),
        ),
        migrations.AddIndex(
            model_name="absenceexcuse",
            index=models.Index(fields=["school", "student"], name="operations__school__09bd41_idx"),
        ),
        migrations.AddIndex(
            model_name="absenceexcuse",
            index=models.Index(
                fields=["student", "date_from"], name="operations__student_e92742_idx"
            ),
        ),
        migrations.RunSQL(sql=ENABLE, reverse_sql=DISABLE),
    ]
