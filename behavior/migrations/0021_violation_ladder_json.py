from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("behavior", "0020_conduct_4_07_name_from_source"),
    ]

    operations = [
        migrations.AddField(
            model_name="violationcategory",
            name="ladder_key",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="مثال: d4_danger — يحدّد السلّم المشترَك بين المخالفات",
                max_length=50,
                verbose_name="مفتاح السلّم",
            ),
        ),
        migrations.AddField(
            model_name="violationcategory",
            name="ladder_json",
            field=models.JSONField(
                blank=True,
                help_text="بنيةٌ قابلةٌ للاستعلام: {ladder_key, pages, max_reps, steps, beyond, notes}",
                null=True,
                verbose_name="سلّم الإجراءات (JSON)",
            ),
        ),
    ]
