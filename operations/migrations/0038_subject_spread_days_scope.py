# الفنّيّةُ مزدوجةٌ في الإعداديّ ومتباعدةٌ في الثانويّ (قرار 2026-09-08) —
# وحقلُ الازدواج وحدَه لا يسع الحالين، فصار للتباعد نطاقُ مرحلة.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0037_assignment_unique_per_teacher"),
    ]

    operations = [
        migrations.AddField(
            model_name="subject",
            name="spread_days_scope",
            field=models.CharField(
                choices=[
                    ("none", "لا"),
                    ("prep", "الإعدادي"),
                    ("sec", "الثانوي"),
                    ("all", "كل المراحل"),
                ],
                default="none",
                help_text="لا تجتمع حصّتان منها في يومٍ واحدٍ للشعبة — في المرحلة المختارة",
                max_length=4,
                verbose_name="حصصها في أيام مختلفة",
            ),
        ),
    ]
