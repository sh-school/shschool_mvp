"""[B4-3B] `undeliverable` — تدخل مع من يكتبها لا قبله.

الحالة تصف تسليماً لا وجهة صالحة له، ولا إعادةَ محاولة تُحسّن ذلك. وليست
فشلاً: النظام سليم والمستلم بلا عنوان يعمل على هذه القناة.

منتجاها في هذه الدفعة نفسها، وكلاهما في Push: مستخدم بلا اشتراكات فعّالة
إطلاقاً — فلا محاولة مزوّد ولا سجلّ محاولة — ومستخدم ردّ المزوّد على كل
اشتراكاته بـ404/410، فالمحاولات جرت وسُجّلت وأثبتت أن الوجهات ميتة.

ولا `unknown_outcome` هنا: مكتشفها المُصالِح في B4-4.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0012_delivery_lease"),
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
                ],
                db_index=True,
                default="pending",
                max_length=15,
                verbose_name="الحالة",
            ),
        ),
    ]
