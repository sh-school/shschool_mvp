import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ImportBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file_fingerprint", models.CharField(db_index=True, max_length=64, verbose_name="بصمة الملفّين")),
                ("row_count", models.PositiveIntegerField(verbose_name="الصفوف المقروءة")),
                ("created_count", models.PositiveIntegerField(verbose_name="المُنشأ")),
                ("names_masked", models.BooleanField(default=False, verbose_name="حُجبت أسماءٌ من قائمة")),
                ("imported_at", models.DateTimeField(auto_now_add=True, verbose_name="وقت الاستيراد")),
            ],
            options={
                "verbose_name": "دفعة استيراد قرارات",
                "verbose_name_plural": "دفعات استيراد القرارات",
                "ordering": ["-imported_at"],
            },
        ),
        migrations.CreateModel(
            name="Decision",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("decision_id", models.CharField(max_length=64, unique=True, verbose_name="المعرّف")),
                ("decided_at_text", models.CharField(blank=True, max_length=64, verbose_name="التاريخ كما في المصدر")),
                ("text", models.TextField(verbose_name="النصّ (بعد حجب الشخصيّ)")),
                ("effect", models.TextField(blank=True, verbose_name="الأثر")),
                ("reference", models.CharField(blank=True, max_length=255, verbose_name="المرجع")),
                (
                    "kind",
                    models.CharField(
                        blank=True,
                        choices=[("approval", "اعتماد"), ("structural", "بنيوي")],
                        max_length=16,
                        verbose_name="النوع",
                    ),
                ),
                ("location", models.CharField(blank=True, max_length=255, verbose_name="الموضع")),
                ("source_ts", models.CharField(blank=True, max_length=40, verbose_name="وقت الوصف الوصفي")),
                ("fingerprint", models.CharField(db_index=True, max_length=64, verbose_name="البصمة")),
                ("imported_at", models.DateTimeField(auto_now_add=True, verbose_name="وقت الاستيراد")),
                (
                    "batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="decisions",
                        to="decisions_registry.importbatch",
                        verbose_name="الدفعة",
                    ),
                ),
            ],
            options={
                "verbose_name": "قرار مالك",
                "verbose_name_plural": "قرارات المالك",
                "ordering": ["decision_id"],
            },
        ),
    ]
