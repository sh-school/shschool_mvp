# Session لا يعرف مجموعةَ الاختيار، فقيدُه الفريد (الشعبة، التاريخ، الوقت) يُسقط
# الحصّةَ الثانية من كلّ زوج اختيارٍ بصمتٍ في `bulk_create(ignore_conflicts=True)`:
# الأربعاء 178 حصّةً في الجدول مقابل 175 جلسة، وأحدُ المعلّمَين لا يجد حصّته.
# الحقلُ نفسُه في ScheduleSlot منذ 0024، ويُورَّث الآن إلى الجلسة.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0028_teacherpreference_max_gap"),
    ]

    operations = [
        migrations.AddField(
            model_name="session",
            name="elective_group",
            field=models.CharField(
                blank=True, default="", max_length=40, verbose_name="مجموعة الاختيار"
            ),
        ),
        migrations.RemoveConstraint(
            model_name="session",
            name="no_class_time_overlap",
        ),
        migrations.AddConstraint(
            model_name="session",
            constraint=models.UniqueConstraint(
                fields=("class_group", "date", "start_time", "elective_group"),
                name="no_class_time_overlap",
            ),
        ),
    ]
