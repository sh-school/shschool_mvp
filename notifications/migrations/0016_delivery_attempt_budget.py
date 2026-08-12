"""[B4-4] ميزانية المحاولات تنتقل من الرسالة إلى الصفّ.

كانت الميزانية `request.retries` داخل رسالة Celery وحدها. وذلك كان كافياً ما
دام لا أحد يُنشئ رسالةً جديدة لنفس التسليم — ثم صار للمُصالِح أن يُعيد طبر
`retry_wait`، والمهمّة الجديدة تبدأ من صفر. فلو تكرّر فشلُ نشر الإعادة بعد كتابة
`retry_wait`، أعاد المُصالِح دورةً كاملة كلّ مرّة: لا حدّ فعليّ للمحاولات.

والصفوف القائمة تبدأ من صفر لا من عددها الحقيقي، وهذا مقبول: الراية مطفأة في كل
بيئة، فلا تسليم متتبَّع في الإنتاج أصلاً — والبديل، استنتاجُ العدد من
`NotificationLog`، كان سيُغفل بالضبط المحاولات التي مات فيها العامل قبل الكتابة.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0015_delivery_unknown_outcome"),
    ]

    operations = [
        migrations.AddField(
            model_name="notificationdelivery",
            name="attempt_count",
            field=models.PositiveIntegerField(default=0, verbose_name="عدد المحاولات"),
        ),
    ]
