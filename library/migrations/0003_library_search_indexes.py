"""
Migration: 0003_library_search_indexes
Indexes على جداول المكتبة لتسريع البحث.
"""
from django.db import migrations, models
import django.contrib.postgres.indexes


class Migration(migrations.Migration):

    dependencies = [
        ("library", "0002_alter_bookborrowing_id_alter_libraryactivity_id_and_more"),
        # pg_trgm يجب أن يُفعَّل أولاً قبل إنشاء gin_trgm_ops indexes
        ("core", "0012_search_indexes_and_pg_trgm"),
    ]

    operations = [
        # GIN Trigram على title — بحث ذكي في عنوان الكتاب
        migrations.AddIndex(
            model_name="librarybook",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["title"],
                name="book_title_gin_trgm_idx",
                opclasses=["gin_trgm_ops"],
            ),
        ),
        # GIN Trigram على author
        migrations.AddIndex(
            model_name="librarybook",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["author"],
                name="book_author_gin_trgm_idx",
                opclasses=["gin_trgm_ops"],
            ),
        ),
        # BTree على book_type — فلترة سريعة
        migrations.AddIndex(
            model_name="librarybook",
            index=models.Index(
                fields=["book_type"],
                name="book_type_btree_idx",
            ),
        ),
        # BTree على available_qty — فلترة الكتب المتاحة
        migrations.AddIndex(
            model_name="librarybook",
            index=models.Index(
                fields=["available_qty"],
                name="book_available_qty_btree_idx",
            ),
        ),
        # BTree على borrowing status
        migrations.AddIndex(
            model_name="bookborrowing",
            index=models.Index(
                fields=["status", "due_date"],
                name="borrowing_status_due_idx",
            ),
        ),
    ]
