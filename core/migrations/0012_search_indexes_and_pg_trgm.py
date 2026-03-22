"""
Migration: 0012_search_indexes_and_pg_trgm
==========================================
تفعيل امتداد pg_trgm وإضافة GIN indexes للبحث الذكي.

ملاحظة: national_id و full_name لديهما db_index=True في الـ model
       لذا الـ BTree indexes موجودة — نُضيف فقط GIN للبحث الذكي.
"""
from django.db import migrations, models
import django.contrib.postgres.indexes
import django.contrib.postgres.operations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0011_alter_customuser_national_id_alter_customuser_phone"),
    ]

    operations = [
        # ── تفعيل امتداد pg_trgm (مطلوب للبحث بالتشابه) ─────────────────
        django.contrib.postgres.operations.TrigramExtension(),

        # ── GIN Trigram على full_name — بحث ذكي مع أخطاء إملائية ─────────
        migrations.AddIndex(
            model_name="customuser",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["full_name"],
                name="user_full_name_gin_trgm_idx",
                opclasses=["gin_trgm_ops"],
            ),
        ),

        # ── is_active — فلترة المستخدمين النشطين (إن لم تكن موجودة) ───────
        migrations.AddIndex(
            model_name="customuser",
            index=models.Index(
                fields=["is_active"],
                name="user_is_active_btree_idx",
            ),
        ),

        # ── Membership — فلترة مدرسة + نشط ──────────────────────────────
        migrations.AddIndex(
            model_name="membership",
            index=models.Index(
                fields=["school", "is_active"],
                name="membership_school_active_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="membership",
            index=models.Index(
                fields=["user", "school"],
                name="membership_user_school_idx",
            ),
        ),

        # ── AuditLog — بحث ومراقبة ───────────────────────────────────────
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(
                fields=["school", "timestamp"],
                name="auditlog_school_timestamp_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(
                fields=["user", "action"],
                name="auditlog_user_action_idx",
            ),
        ),
    ]
