from django.db import migrations, models


class Migration(migrations.Migration):
    """توسيعٌ فقط (W-20261012-027): وسمُ التقييم الذاتي لحصّةٍ خارج جدول المعلّم. افتراضه False فلا يمسّ صفّاً قائماً."""

    dependencies = [
        ("quality", "0023_arabic_field_labels"),
    ]

    operations = [
        migrations.AddField(
            model_name="classroomobservation",
            name="outside_schedule",
            field=models.BooleanField(default=False, verbose_name="حصّة خارج جدولي"),
        ),
    ]
