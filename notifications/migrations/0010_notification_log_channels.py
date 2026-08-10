"""Give WhatsApp and Push their own channel values, and correct the past.

`NotificationLog.CHANNEL` offered only `email` and `sms`. WhatsApp was therefore
recorded as `channel="sms"` — with a comment in the source admitting it — and
Push wrote no row at all. Two of the four external channels were not
representable in the column meant to name them.

The historical rows are correctable without guessing. `_send_whatsapp` is the
only writer that prefixes `recipient` with `whatsapp:`, so a row that carries
that prefix and claims `sms` is a WhatsApp delivery mislabelled by the missing
choice, not an SMS. Rows without the prefix are left alone.

Leaving them would keep every count of "SMS sent" quietly inflated by WhatsApp
traffic, and would leave the column disagreeing with the row it describes.
"""

from django.db import migrations, models

WHATSAPP_RECIPIENT_PREFIX = "whatsapp:"


def relabel_whatsapp_rows(apps, schema_editor):
    """Rows written by `_send_whatsapp` before `whatsapp` was a valid choice."""
    NotificationLog = apps.get_model("notifications", "NotificationLog")

    NotificationLog.objects.filter(
        channel="sms",
        recipient__startswith=WHATSAPP_RECIPIENT_PREFIX,
    ).update(channel="whatsapp")


def restore_whatsapp_rows(apps, schema_editor):
    """Reverse puts them back under `sms`, which is what the old choices allow."""
    NotificationLog = apps.get_model("notifications", "NotificationLog")

    NotificationLog.objects.filter(
        channel="whatsapp",
        recipient__startswith=WHATSAPP_RECIPIENT_PREFIX,
    ).update(channel="sms")


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0009_alter_deadlettermessage_kind"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notificationlog",
            name="channel",
            field=models.CharField(
                choices=[
                    ("email", "بريد إلكتروني"),
                    ("sms", "SMS"),
                    ("whatsapp", "WhatsApp"),
                    ("push", "Push"),
                ],
                default="email",
                max_length=10,
            ),
        ),
        migrations.RunPython(relabel_whatsapp_rows, restore_whatsapp_rows),
    ]
