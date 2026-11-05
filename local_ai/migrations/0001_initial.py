"""وثائقُ المعرفة ومقاطعُها — الهجرةُ الأولى لتطبيق local_ai (توسيعٌ خالص: جدولان جديدان).

كُتبت يدويّاً على تعريفات `local_ai/models.py`؛ تحقّق منها `makemigrations --check --dry-run`.
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("core", "0086_elective_group_membership"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="KnowledgeDocument",
            fields=[
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="تاريخ التعديل")),
                ("title", models.CharField(max_length=200, verbose_name="العنوان")),
                ("file", models.FileField(upload_to="local_ai/%Y/%m/", verbose_name="الملفّ")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "بانتظار الفهرسة"),
                            ("indexing", "قيد الفهرسة"),
                            ("ready", "جاهز"),
                            ("failed", "فشل"),
                        ],
                        default="pending",
                        max_length=10,
                        verbose_name="الحالة",
                    ),
                ),
                ("error_message", models.TextField(blank=True, default="", verbose_name="سببُ الفشل")),
                ("summary", models.TextField(blank=True, default="", verbose_name="الملخّص")),
                ("metadata", models.JSONField(blank=True, default=dict, verbose_name="بيانات مستخرَجة")),
                ("chunk_count", models.PositiveIntegerField(default=0, verbose_name="عددُ المقاطع")),
                ("indexed_at", models.DateTimeField(blank=True, null=True, verbose_name="وقتُ الفهرسة")),
                ("is_active", models.BooleanField(default=True, verbose_name="مفعَّلة")),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(app_label)s_%(class)s_set",
                        to="core.school",
                        verbose_name="المدرسة",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="local_ai_documents",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="رفعه",
                    ),
                ),
            ],
            options={
                "verbose_name": "وثيقة معرفة",
                "verbose_name_plural": "وثائق المعرفة",
                "ordering": ["-created_at"],
                "abstract": False,
                "indexes": [
                    models.Index(fields=["school", "status"], name="local_ai_doc_school_status")
                ],
            },
        ),
        migrations.CreateModel(
            name="DocumentChunk",
            fields=[
                (
                    "id",
                    models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                ("ordinal", models.PositiveIntegerField(verbose_name="الترتيب")),
                ("text", models.TextField(verbose_name="النصّ")),
                ("char_count", models.PositiveIntegerField(default=0, verbose_name="عددُ الحروف")),
                ("embedding", models.JSONField(verbose_name="متّجه التضمين")),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chunks",
                        to="local_ai.knowledgedocument",
                        verbose_name="الوثيقة",
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="local_ai_chunks",
                        to="core.school",
                        verbose_name="المدرسة",
                    ),
                ),
            ],
            options={
                "verbose_name": "مقطع وثيقة",
                "verbose_name_plural": "مقاطع الوثائق",
                "ordering": ["document", "ordinal"],
                "constraints": [
                    models.UniqueConstraint(fields=("document", "ordinal"), name="local_ai_chunk_unique_ordinal")
                ],
            },
        ),
    ]
