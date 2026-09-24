"""مفتاحُ وقف الإسناد عن المنسّقين — توسيعٌ صرف (P4-1): أعمدةٌ جديدةٌ بلا حذفٍ ولا تغيير."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academic_management", "0007_rls_course_preparation"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="workloadgovernance",
            name="coordinator_entry_paused",
            field=models.BooleanField(
                default=False,
                help_text="متى كان مفعّلاً لا يُدخل المنسّقون إسناداً ولا يرفعونه",
                verbose_name="الإسنادُ موقوفٌ عن المنسّقين",
            ),
        ),
        migrations.AddField(
            model_name="workloadgovernance",
            name="entry_changed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="workloadgovernance",
            name="entry_changed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
