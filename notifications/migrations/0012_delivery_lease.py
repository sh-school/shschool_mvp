"""[B4-3A] حقول الاستئجار وزمن آخر انتقال على `NotificationDelivery`.

`lease_token` رمز سياج لا قفل: العامل لا يُنهي تسليماً إلا وهو ما زال يحمل
الرمز الذي أخذه عند الاستحواذ، فلا يعود عاملٌ بطيء بعد انتقال الملكية ليهدم
حالةً أحدث منه.

و`status_changed_at` يُردَم من `created_at` لا من `now()`. الصفّ لم يتغيّر لحظة
الترحيل، وكتابة زمنٍ لم يقع فيه انتقال هي بالضبط الادّعاء الذي تُبنى ضده هذه
السلسلة. عدد الصفوف اليوم صفر لأن الراية مُطفأة، لكن ذلك ليس مبرّراً لتخطّي
الردم — قاعدة تطوير أو صفٌّ يُكتب بين الآن والنشر يجب أن يسلك السلوك نفسه.

ولا `auto_now=True` عليه. الانتقالات في B4-3 تجري بـ`QuerySet.update()` لأنها
تحتاج أن تكون ذرّية، و`auto_now` لا يعمل مع `update()`: حقلٌ يبدو محدَّثاً
تلقائياً ولا يُحدَّث أسوأ من غيابه. فالكتابة صريحة في كل انتقال.
"""

import django.utils.timezone
from django.db import migrations, models
from django.db.models import F


def backfill_status_changed_at(apps, schema_editor):
    """آخر انتقال للصفوف القائمة هو لحظة إنشائها — لا لحظة الترحيل."""
    NotificationDelivery = apps.get_model("notifications", "NotificationDelivery")

    NotificationDelivery.objects.filter(status_changed_at__isnull=True).update(
        status_changed_at=F("created_at")
    )


def unbackfill(apps, schema_editor):
    """التراجع يُسقط العمود؛ إفراغه قبل ذلك لا معنى له."""


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0011_dispatch_delivery_schema"),
    ]

    operations = [
        migrations.AddField(
            model_name="notificationdelivery",
            name="lease_token",
            field=models.UUIDField(blank=True, null=True, verbose_name="رمز الاستئجار"),
        ),
        migrations.AddField(
            model_name="notificationdelivery",
            name="lease_expires_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="انتهاء الاستئجار"),
        ),
        migrations.AddField(
            model_name="notificationdelivery",
            name="status_changed_at",
            field=models.DateTimeField(null=True, verbose_name="آخر انتقال"),
        ),
        migrations.RunPython(backfill_status_changed_at, unbackfill),
        migrations.AlterField(
            model_name="notificationdelivery",
            name="status_changed_at",
            field=models.DateTimeField(
                default=django.utils.timezone.now, verbose_name="آخر انتقال"
            ),
        ),
    ]
