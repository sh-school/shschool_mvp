"""اسمُ المخالفة 4-07 كما في ص117 من الدليل التنظيميّ لسياسة إدارة سلوك الطلبة 2026.

كتبت هجرةُ 0015 الاسمَ من `CATALOG` يومَ كان «(السجائر والسجائر والشيشة الإلكترونيّة)»؛
والمصدرُ: «(السجائر / السجائر الإلكترونيّة / الشيشة الإلكترونيّة / السويكة أو ما شابه)».
فتصحيحُ `CATALOG` وحدَه لا يصل قاعدةً هُجِّرت من قبلُ — وهذه تُلحقها به.

الرمزُ ومعناه لم يتغيّرا، فيُحدَّث الاسمُ في مكانه (لا `25-<الرمز>` كما تفعل 0015 لمعنىً مختلف).
ولا يُمسّ اسمٌ عدّله أحدٌ بيده: الشرطُ أن يكون الاسمُ الحاليّ هو القديمَ حرفيّاً.
"""

from django.db import migrations

CODE = "4-07"
OLD_NAME = "حيازة الممنوعات (السجائر والسجائر والشيشة الإلكترونيّة) أو تعاطيها أو الترويج لها"
NEW_NAME = (
    "حيازة الممنوعات (السجائر / السجائر الإلكترونيّة / الشيشة الإلكترونيّة / السويكة أو ما شابه) "
    "أو تعاطيها أو الترويج لها"
)


def forwards(apps, schema_editor):
    ViolationCategory = apps.get_model("behavior", "ViolationCategory")
    ViolationCategory.objects.filter(code=CODE, name_ar=OLD_NAME).update(name_ar=NEW_NAME)


def backwards(apps, schema_editor):
    ViolationCategory = apps.get_model("behavior", "ViolationCategory")
    ViolationCategory.objects.filter(code=CODE, name_ar=NEW_NAME).update(name_ar=OLD_NAME)


class Migration(migrations.Migration):
    dependencies = [
        ("behavior", "0019_arabic_field_labels"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
