"""[W-20260929-011] الإصدار الأول لتقليص العمود القديم blood_type.

خطوتان بلا حذفٍ للعمود:
  ١) افتراضٌ فارغٌ على مستوى القاعدة، فتعمل نسخةٌ قديمةٌ من الشيفرة تُدرج صفّاً
     بلا هذا العمود أثناء النشر المتدحرج.
  ٢) إزالةُ الحقل من **حالة** النموذج وحدها (بلا عملية على القاعدة)، فيبقى العمود.

حذفُ العمود هجرةٌ منفصلةٌ لاحقة، بعد ثلاثة أيام من نشر هذا الإصدار وبحكم 0105
واعتماد المالك.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clinic", "0010_healthrecord_needs_care"),
    ]

    operations = [
        migrations.AlterField(
            model_name="healthrecord",
            name="blood_type",
            field=models.CharField(
                blank=True,
                db_default="",
                default="",
                max_length=3,
                verbose_name="فصيلة الدم (قديم)",
            ),
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name="healthrecord", name="blood_type"),
            ],
        ),
    ]
