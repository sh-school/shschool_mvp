"""[B4-4] `unknown_outcome` — تدخل مع مَن يكتبها لا قبله.

الحالة تصف تسليماً دخل منطقة المزوّد ثم انقضى استئجاره بلا نهاية مكتوبة. وهي
انعدامُ معرفة لا فشل: قد يكون المزوّد قبِل الرسالة قبل موت العامل، وقد لا يكون.

وكاتبها الوحيد هو المُصالِح، ولا يُعيد تسليماً بلغها أبداً. الفرق بين هذه وبين
`pending` المعلّقة هو الحدّ كلّه: `pending` لم يدخلها عاملٌ قطّ، فإعادةُ طبرها
أسوأ ما تُنتج رسالةٌ مكرّرة في الوسيط يحتملها سياج التسليم — أمّا هذه فإعادتها
مقامرةٌ برسالة مكرّرة تصل إلى إنسان.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0014_enqueue_intent"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notificationdelivery",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "معلّق"),
                    ("in_progress", "قيد التنفيذ"),
                    ("sent", "سُلّم"),
                    ("retry_wait", "بانتظار إعادة المحاولة"),
                    ("dead_lettered", "استنفد المحاولات"),
                    ("undeliverable", "لا وجهة صالحة"),
                    ("unknown_outcome", "نتيجة غير معروفة"),
                ],
                db_index=True,
                default="pending",
                max_length=15,
                verbose_name="الحالة",
            ),
        ),
    ]
