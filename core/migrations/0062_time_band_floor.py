"""طابقُ الجرس — والقائمُ في القاعدة يُصحَّح، لا يُترك على الافتراض.

الحقلُ افتراضُه `ground`، وهو صوابٌ لجرسٍ واحدٍ من الثلاثة وخطأٌ في اثنين:
`ninth` و`secondary` كلاهما في الطابق الأوّل. فترقيةٌ بلا تصحيحٍ تُخرج قاعدةً
تقول إنّ المدرسةَ كلَّها طابقٌ أرضيّ — وتسكت.

و`seed_time_bands` يكتب الطابقَ من اليوم، لكنّ الاعتمادَ على تذكُّر تشغيلِ أمرٍ
بعد النشر ليس ضماناً. فالتصحيحُ في الهجرة يسري حيث تسري الترقية.

والرموزُ الثلاثةُ مكتوبةٌ هنا لأنّها **حالُ القاعدة يوم كُتبت الهجرة** لا قاعدةٌ
عامّة: ما لا يُعرف رمزُه يُترك على الافتراض ويُصحَّح من لوحة الإدارة.
"""

from django.db import migrations, models

#: رمزُ الجرس → طابقُه. حالُ 2026-09-12، وما ليس فيها يبقى على افتراضه.
FLOOR_OF_CODE = {"ground": "ground", "ninth": "first", "secondary": "first"}


def set_floors(apps, schema_editor):
    TimeBand = apps.get_model("core", "TimeBand")
    for code, floor in FLOOR_OF_CODE.items():
        TimeBand.objects.filter(code=code).update(floor=floor)


def unset_floors(apps, schema_editor):
    """الرجوعُ يحذف الحقلَ نفسَه — فلا شيءَ يُعاد."""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0061_wing_entity"),
    ]

    operations = [
        migrations.AddField(
            model_name="timeband",
            name="floor",
            field=models.CharField(
                choices=[("ground", "الطابق الأرضيّ"), ("first", "الطابق الأوّل")],
                default="ground",
                max_length=6,
                verbose_name="الطابق",
            ),
        ),
        migrations.RunPython(set_floors, unset_floors),
    ]
