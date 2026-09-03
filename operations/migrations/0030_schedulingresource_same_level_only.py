# الملعبانِ يتقاسمهما الإعداديّ والثانويّ، لكن لا في التوقيت نفسه: حصّتا
# بدنيّةٍ متزامنتان تكونان من مرحلةٍ واحدة (قرار الإدارة 2026-09-03).
# السعةُ تقول «اثنتان»، وهذه الرايةُ تقول «اثنتان من جنسٍ واحد».

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0029_session_elective_group"),
    ]

    operations = [
        migrations.AddField(
            model_name="schedulingresource",
            name="same_level_only",
            field=models.BooleanField(
                default=False,
                verbose_name="مرحلةٌ واحدةٌ في التوقيت (لا يجتمع إعداديّ وثانويّ)",
            ),
        ),
    ]
