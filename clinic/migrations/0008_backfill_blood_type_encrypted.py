"""[W-029] ملء: ينقل فصيلةَ الدم من العمود الصريح إلى الحقل المشفَّر ويفرّغ القديم.

النموذجُ التاريخيُّ هنا يملك `EncryptedTextField`، فيشفّر `save()` القيمةَ عند
الكتابة (لا ثلاثيّةَ يدويّة كما في حقول الهويّة). ومُعاوِد: لا يمسّ إلا صفّاً
فيه قيمةٌ قديمةٌ وحقلُه المشفَّر فارغ. والعكسُ يردّ القيمةَ إلى العمود القديم.
جدولٌ من بضعة صفوف؛ لا حاجةَ إلى دفعات.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    HealthRecord = apps.get_model("clinic", "HealthRecord")
    for record in HealthRecord.objects.exclude(blood_type="").iterator():
        if not record.blood_type_encrypted:
            record.blood_type_encrypted = record.blood_type
        # القديمُ يُفرَّغ دائماً: النصُّ الصريح لا يبقى بعد نقله.
        record.blood_type = ""
        record.save(update_fields=["blood_type", "blood_type_encrypted"])


def backwards(apps, schema_editor):
    HealthRecord = apps.get_model("clinic", "HealthRecord")
    for record in HealthRecord.objects.exclude(blood_type_encrypted="").iterator():
        record.blood_type = record.blood_type_encrypted
        record.save(update_fields=["blood_type"])


class Migration(migrations.Migration):
    dependencies = [
        ("clinic", "0007_healthrecord_blood_type_encrypted"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
