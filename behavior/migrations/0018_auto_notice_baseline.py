"""خطُّ الإطلاق: ما رصده الكشفُ قبل هذه الهجرة لا يُرسَل إلى الأسرة.

كشفُ الحصص يكتب مخالفاتٍ آليّةً منذ ما قبل قرار الإبلاغ، وجدولُ العلامات يُنشأ
فارغاً (`0017`). فلولا هذا لرأى أوّلُ تشغيلٍ بعد النشر كلَّ تأخّرٍ في الأيّام
الخمسة الماضية «لم يُبلَّغ به بعدُ»، فأرسل لكلّ طالبٍ خمسَ رسائلَ عن أسبوعٍ مضى.
ونافذةُ الأيّام الخمسة وُضعت لتدارك تشغيلٍ فائتٍ وتصحيحٍ متأخّر، لا لاستدراك
ما قبل القرار.

فتُكتب لكلّ مخالفةٍ آليّةٍ قائمةٍ علامةُ `baseline` بمفتاحها (الطالب، يوم الحصّة،
القاعدة، بدء الحصّة) وبلا مستلمين. والهروبُ من المدرسة معها: تصحيحٌ بعد الإطلاق
يحذف هروباً قديماً ثمّ يُعيده ليس حدثاً جديداً.

والهجرةُ تجري بصاحب الجداول، والعزلُ غيرُ مفروضٍ عليه (`ENABLE` لا `FORCE`)،
فترى المدارسَ كلَّها. وتُعاد بلا أثر: القيدُ الفريدُ يُسقط المكرَّر.
"""

import uuid

from django.db import migrations, models

BATCH = 1000


def mark_existing(apps, schema_editor):
    BehaviorInfraction = apps.get_model("behavior", "BehaviorInfraction")
    AutoInfractionNotice = apps.get_model("behavior", "AutoInfractionNotice")

    rows = (
        BehaviorInfraction.objects.exclude(auto_rule="")
        .filter(session__isnull=False)
        .values_list(
            "id", "school_id", "student_id", "auto_rule", "session__date", "session__start_time"
        )
        .order_by("id")
    )
    seen = set()
    batch = []
    for pk, school_id, student_id, rule, day, start in rows.iterator(chunk_size=BATCH):
        key = (student_id, day, rule, start)
        if key in seen:
            continue
        seen.add(key)
        batch.append(
            AutoInfractionNotice(
                id=uuid.uuid4(),
                school_id=school_id,
                student_id=student_id,
                date=day,
                auto_rule=rule,
                start_time=start,
                infraction_id=pk,
                message_id=uuid.uuid4(),
                kind="baseline",
                recipients=None,
            )
        )
        if len(batch) >= BATCH:
            AutoInfractionNotice.objects.bulk_create(batch, ignore_conflicts=True)
            batch = []
    if batch:
        AutoInfractionNotice.objects.bulk_create(batch, ignore_conflicts=True)


def unmark(apps, schema_editor):
    apps.get_model("behavior", "AutoInfractionNotice").objects.filter(kind="baseline").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("behavior", "0017_auto_infraction_notice"),
    ]

    operations = [
        migrations.AlterField(
            model_name="autoinfractionnotice",
            name="kind",
            field=models.CharField(
                choices=[
                    ("immediate", "فوريّ"),
                    ("digest", "الملخّص اليوميّ"),
                    ("supplement", "إضافةٌ إلى الملخّص"),
                    ("baseline", "سابقٌ للإطلاق — لم يُرسَل"),
                ],
                max_length=10,
            ),
        ),
        migrations.RunPython(mark_existing, unmark),
    ]
