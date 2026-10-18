# Generated for W-20261017-024

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0086_absence_followup_options_and_status"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="absenceactionlog",
            name="followed_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="وقتُ المتابعة"),
        ),
        migrations.AddField(
            model_name="absenceactionlog",
            name="followed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="absence_actions_followed",
                to=settings.AUTH_USER_MODEL,
                verbose_name="من تابع",
            ),
        ),
    ]
