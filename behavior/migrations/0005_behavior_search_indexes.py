"""
Migration: 0005_behavior_search_indexes
Indexes على جداول السلوك لتسريع الفلترة والبحث.
"""
from django.db import migrations, models
import django.contrib.postgres.indexes


class Migration(migrations.Migration):

    dependencies = [
        ("behavior", "0004_alter_behaviorinfraction_action_taken_and_more"),
        # pg_trgm يجب أن يُفعَّل أولاً قبل إنشاء gin_trgm_ops indexes
        ("core", "0012_search_indexes_and_pg_trgm"),
    ]

    operations = [
        # BTree على date — فلترة زمنية سريعة
        migrations.AddIndex(
            model_name="behaviorinfraction",
            index=models.Index(
                fields=["date"],
                name="infraction_date_btree_idx",
            ),
        ),
        # BTree على level — فلترة حسب الدرجة
        migrations.AddIndex(
            model_name="behaviorinfraction",
            index=models.Index(
                fields=["level"],
                name="infraction_level_btree_idx",
            ),
        ),
        # مركّب: student + date — الاستعلام الأكثر شيوعاً
        migrations.AddIndex(
            model_name="behaviorinfraction",
            index=models.Index(
                fields=["student", "date"],
                name="infraction_student_date_idx",
            ),
        ),
        # مركّب: school + level — إحصائيات المدرسة
        migrations.AddIndex(
            model_name="behaviorinfraction",
            index=models.Index(
                fields=["school", "level"],
                name="infraction_school_level_idx",
            ),
        ),
        # GIN Trigram على description — بحث في النص
        migrations.AddIndex(
            model_name="behaviorinfraction",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["description"],
                name="infraction_description_gin_idx",
                opclasses=["gin_trgm_ops"],
            ),
        ),
    ]
