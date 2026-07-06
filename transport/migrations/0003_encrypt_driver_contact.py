"""[PII-09] تشفير هاتف السائق ورابط GPS في SchoolBus (Fernet at-rest).

قراءة/كتابة خام عبر cursor مع حارس ضد التشفير المزدوج وعكس قابل للتنفيذ.
"""
from django.db import migrations

import core.fields

_COLS = ("driver_phone", "gps_link")


def _apply(apps, schema_editor, *, encrypt):
    from core.models import decrypt_field, encrypt_field

    Model = apps.get_model("transport", "SchoolBus")
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
        ("transport", "0002_alter_busroute_id_alter_schoolbus_id"),
    ]

    operations = [
        migrations.AlterField(
            model_name="schoolbus",
            name="driver_phone",
            field=core.fields.EncryptedTextField(verbose_name="جوال السائق"),
        ),
        migrations.AlterField(
            model_name="schoolbus",
            name="gps_link",
            field=core.fields.EncryptedTextField(blank=True, verbose_name="رابط التتبع (GPS)"),
        ),
        migrations.RunPython(forward, backward),
    ]
