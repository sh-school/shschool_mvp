import notifications.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0006_add_parent_summon_event_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="DeadLetterMessage",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=notifications.models._uuid,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[("email", "بريد"), ("sms", "SMS"), ("push", "Push")],
                        max_length=10,
                    ),
                ),
                ("payload", models.JSONField(default=dict)),
                ("error", models.TextField(blank=True)),
                ("resolved", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "رسالة فاشلة (DLQ)",
                "verbose_name_plural": "رسائل فاشلة (DLQ)",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="deadlettermessage",
            index=models.Index(
                fields=["resolved", "created_at"], name="notif_dlq_resolved_idx"
            ),
        ),
    ]
