"""W-20261117-002: تشفير اسم المتصل وصلته في ورقة الخروج بالحقل المشفَّر نفسه الذي يحمل رقم الاتّصال.

توسيعٌ (العمودان يصيران نصّاً مشفَّراً) ثمّ تقليصٌ (تُشفَّر القيمُ الموجودة في مكانها بلا فقد)؛
والتراجعُ يفكّ التشفير بسطرٍ خام قبل أن يعود العمودُ محدودَ الطول.
"""

from django.db import migrations

import core.fields


def encrypt_existing(apps, schema_editor):
    """القراءةُ متسامحةٌ مع النصّ الصريح والكتابةُ تُشفّر؛ فإعادةُ التشغيل لا تُشفّر مرّتين."""
    model = apps.get_model("operations", "ExitPermit")
    rows = model.objects.exclude(caller_name="", caller_relation="").values_list(
        "pk", "caller_name", "caller_relation"
    )
    for pk, name, relation in list(rows):
        model.objects.filter(pk=pk).update(caller_name=name, caller_relation=relation)


def decrypt_existing(apps, schema_editor):
    from core.models import decrypt_field

    model = apps.get_model("operations", "ExitPermit")
    table = schema_editor.quote_name(model._meta.db_table)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"SELECT id, caller_name, caller_relation FROM {table}")  # noqa: S608
        rows = cursor.fetchall()
        for pk, name, relation in rows:
            cursor.execute(
                f"UPDATE {table} SET caller_name = %s, caller_relation = %s WHERE id = %s",  # noqa: S608
                [decrypt_field(name or "")[:150], decrypt_field(relation or "")[:40], pk],
            )


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0099_exit_permit_guardian_method"),
    ]

    operations = [
        migrations.AlterField(
            model_name="exitpermit",
            name="caller_name",
            field=core.fields.EncryptedTextField(
                blank=True, db_default="", default="", verbose_name="اسم المتصل"
            ),
        ),
        migrations.AlterField(
            model_name="exitpermit",
            name="caller_relation",
            field=core.fields.EncryptedTextField(
                blank=True, db_default="", default="", verbose_name="صلة المتصل"
            ),
        ),
        migrations.RunPython(encrypt_existing, decrypt_existing),
    ]
