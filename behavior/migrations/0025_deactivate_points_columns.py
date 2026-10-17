"""W-20261013-010 (المرحلة 1): تعطيلُ أعمدة النقاط دون حذفها (توسيعٌ ثمّ تقليص).

نظامُ حسم الدرجات لا أصلَ له في لوائح الوزارة، وأُزيل كلُّ استعمالٍ له في الشيفرة. تبقى الأعمدةُ
والجدولُ في القاعدة حتى المرحلة 2 (بقرار المالك)، و`db_default=0` يضمن نجاحَ أيّ إدراجٍ بعد
أن كفّ التطبيقُ عن كتابتها. لا تُحذف بياناتٌ هنا.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("behavior", "0024_encrypt_infraction_text")]

    operations = [
        migrations.AlterField(
            model_name="violationcategory",
            name="points",
            field=models.PositiveSmallIntegerField(
                default=0, db_default=0, verbose_name="(مهمل) نقاط مخصومة"
            ),
        ),
        migrations.AlterField(
            model_name="behaviorinfraction",
            name="points_deducted",
            field=models.PositiveSmallIntegerField(
                default=0, db_default=0, verbose_name="(مهمل) نقاط مخصومة"
            ),
        ),
        migrations.AlterField(
            model_name="behaviorpointrecovery",
            name="points_restored",
            field=models.PositiveIntegerField(
                default=0, db_default=0, verbose_name="(مهمل) نقاط مستعادة"
            ),
        ),
    ]
