# U-11 المرحلة 2 (أ): توقيعان على محو بيانات الطالب — مسؤولُ حماية البيانات وحقولُ التوقيع.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _signer(related_name: str, verbose_name: str) -> models.ForeignKey:
    return models.ForeignKey(
        blank=True,
        editable=False,
        null=True,
        on_delete=django.db.models.deletion.SET_NULL,
        related_name=related_name,
        to=settings.AUTH_USER_MODEL,
        verbose_name=verbose_name,
    )


def _signed_at(verbose_name: str) -> models.DateTimeField:
    return models.DateTimeField(blank=True, editable=False, null=True, verbose_name=verbose_name)


class Migration(migrations.Migration):
    dependencies = [("core", "0087_wing_assignment")]

    operations = [
        migrations.AddField(
            model_name="school",
            name="data_protection_officer",
            field=_signer("dpo_of_schools", "مسؤول حماية البيانات"),
        ),
        migrations.AddField(
            model_name="erasurerequest",
            name="admin_signed_by",
            field=_signer("erasure_admin_signed", "موقّع الإدارة"),
        ),
        migrations.AddField(
            model_name="erasurerequest",
            name="admin_signed_at",
            field=_signed_at("وقت توقيع الإدارة"),
        ),
        migrations.AddField(
            model_name="erasurerequest",
            name="dpo_signed_by",
            field=_signer("erasure_dpo_signed", "موقّع حماية البيانات"),
        ),
        migrations.AddField(
            model_name="erasurerequest",
            name="dpo_signed_at",
            field=_signed_at("وقت توقيع حماية البيانات"),
        ),
    ]
