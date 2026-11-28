"""رقمُ نموذج المتابعة: المحفوظُ كلُّه نموذج 19، والمسودةُ المفتوحةُ واحدةٌ لكلّ استمارة."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("quality", "0027_supervisor_followup_send_ack")]

    operations = [
        migrations.AddField(
            model_name="supervisorfollowup",
            name="form_code",
            field=models.CharField(
                db_default="19", default="19", max_length=4, verbose_name="رقم النموذج"
            ),
        ),
        migrations.RemoveConstraint(model_name="supervisorfollowup", name="uniq_supfu_open_draft"),
        migrations.AddConstraint(
            model_name="supervisorfollowup",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_deleted", False), ("status", "draft")),
                fields=("school", "supervisor", "form_code"),
                name="uniq_supfu_open_draft",
            ),
        ),
    ]
