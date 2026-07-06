"""[PII-04] تشفير بيانات جهة اتصال الطوارئ في HealthRecord (Fernet at-rest).

قراءة/كتابة خام عبر cursor (لا عبر الحقل) لتفادي فك التشفير التلقائي، مع حارس ضد
التشفير المزدوج وعكس قابل للتنفيذ (فكّ التشفير).
"""
from django.db import migrations

import core.fields

_COLS = ("emergency_contact_name", "emergency_contact_phone")


def _apply(apps, schema_editor, *, encrypt):
    from core.models import decrypt_field, encrypt_field

    Model = apps.get_model("clinic", "HealthRecord")
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
                dec = decrypt_field(val)  # fail-open: يُعيد المُدخَل عند الفشل ⇒ نصّ صريح
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
        ("clinic", "0003_alter_clinicvisit_reason_alter_clinicvisit_symptoms_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="healthrecord",
            name="emergency_contact_name",
            field=core.fields.EncryptedTextField(blank=True),
        ),
        migrations.AlterField(
            model_name="healthrecord",
            name="emergency_contact_phone",
            field=core.fields.EncryptedTextField(blank=True),
        ),
        migrations.RunPython(forward, backward),
    ]
