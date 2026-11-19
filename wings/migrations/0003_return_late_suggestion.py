import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0086_elective_group_membership"),
        ("wings", "0002_rls_conduct_proposal"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ReturnLateSuggestion",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("week_start", models.DateField(verbose_name="أحدُ الأسبوع")),
                (
                    "late_minutes",
                    models.PositiveIntegerField(default=0, verbose_name="مجموعُ دقائق تأخّر العودة"),
                ),
                (
                    "exit_count",
                    models.PositiveIntegerField(default=0, verbose_name="مرّاتُ الخروج"),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("proposed", "مقترح"),
                            ("accepted", "مقبول"),
                            ("dismissed", "مرفوض"),
                            ("withdrawn", "مسحوب"),
                        ],
                        db_index=True,
                        default="proposed",
                        max_length=10,
                        verbose_name="الحالة",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الاقتراح"),
                ),
                (
                    "decided_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="تاريخ القرار"),
                ),
                (
                    "decided_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="return_late_suggestions_decided",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="من قرّر",
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="return_late_suggestions",
                        to="core.school",
                        verbose_name="المدرسة",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="return_late_suggestions",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="الطالب",
                    ),
                ),
            ],
            options={
                "verbose_name": "اقتراح متابعة تأخّر العودة",
                "verbose_name_plural": "اقتراحات متابعة تأخّر العودة",
                "ordering": ["-week_start", "student_id"],
                "indexes": [
                    models.Index(
                        fields=["school", "status", "week_start"], name="retlate_queue_idx"
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("school", "student", "week_start"),
                        name="uniq_return_late_student_week",
                    )
                ],
            },
        ),
    ]
