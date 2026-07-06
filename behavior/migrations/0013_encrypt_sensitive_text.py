"""[PII-06] تشفير الحقول النصّية الحسّاسة لقاصر في BehaviorInfraction (Fernet at-rest):
وصف المخالفة، ملاحظات الأدلة الرقمية، ملاحظات الإحالة الأمنية.

قراءة/كتابة خام عبر cursor مع حارس ضد التشفير المزدوج وعكس قابل للتنفيذ.
"""
from django.db import migrations

import core.fields

_COLS = ("violation_description", "digital_evidence_notes", "security_notes")


def _apply(apps, schema_editor, *, encrypt):
    from core.models import decrypt_field, encrypt_field

    Model = apps.get_model("behavior", "BehaviorInfraction")
    table = Model._meta.db_table
    pk = Model._meta.pk.column
    with schema_editor.connection.cursor() as cur:
        cur.execute(f"SELECT {pk}, {', '.join(_COLS)} FROM {table}")  # noqa: S608 (أسماء ثابتة)
        rows = cur.fetchall()
        for row in rows:
            rid, vals = row[0], row[1:]
            updates = {}
            for col, val in zip(_COLS, vals, strict=False):
                if not val:
                    continue
                dec = decrypt_field(val)
                if encrypt and dec == val:
                    updates[col] = encrypt_field(val)
                elif not encrypt and dec != val:
                    updates[col] = dec
            if updates:
                sets = ", ".join(f"{c} = %s" for c in updates)
                cur.execute(
                    f"UPDATE {table} SET {sets} WHERE {pk} = %s",  # noqa: S608
                    list(updates.values()) + [rid],
                )


def forward(apps, schema_editor):
    _apply(apps, schema_editor, encrypt=True)


def backward(apps, schema_editor):
    _apply(apps, schema_editor, encrypt=False)


class Migration(migrations.Migration):
    dependencies = [
        ("behavior", "0012_deactivate_legacy_abcd_violations"),
    ]

    operations = [
        migrations.AlterField(
            model_name="behaviorinfraction",
            name="violation_description",
            field=core.fields.EncryptedTextField(
                blank=True,
                default="",
                help_text="مطلوب فقط عند اختيار 'محضر لإثبات المخالفة' (20-2000 حرف)",
                max_length=2000,
                verbose_name="وصف المخالفة (محضر)",
            ),
        ),
        migrations.AlterField(
            model_name="behaviorinfraction",
            name="digital_evidence_notes",
            field=core.fields.EncryptedTextField(
                blank=True,
                default="",
                help_text="وصف الأدلة الرقمية (روابط، لقطات شاشة، إلخ)",
                max_length=1000,
                verbose_name="ملاحظات الأدلة الرقمية",
            ),
        ),
        migrations.AlterField(
            model_name="behaviorinfraction",
            name="security_notes",
            field=core.fields.EncryptedTextField(
                blank=True,
                default="",
                max_length=1000,
                verbose_name="ملاحظات الإحالة الأمنية",
            ),
        ),
        migrations.RunPython(forward, backward),
    ]
