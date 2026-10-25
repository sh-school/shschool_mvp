"""سجلّا متابعة الغياب: `student` يقبل NULL ليُجهَّل الصفُّ عند المحو بدل حذفه (قرارُ المالك، توسيعٌ فقط)."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0084_rls_absence_followup_logs"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="absenceactionlog",
            name="student",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="absence_action_logs",
                to=settings.AUTH_USER_MODEL,
                verbose_name="الطالب",
            ),
        ),
        migrations.AlterField(
            model_name="absencecontactlog",
            name="student",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="absence_contact_logs",
                to=settings.AUTH_USER_MODEL,
                verbose_name="الطالب",
            ),
        ),
    ]
