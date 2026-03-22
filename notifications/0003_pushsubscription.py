"""notifications/migrations/0003_pushsubscription.py"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        (
            "notifications",
            "0002_rename_notif_school_type_idx_notificatio_school__75db48_idx_and_more",
        ),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0009_breachreport"),
    ]
    operations = [
        migrations.CreateModel(
            name="PushSubscription",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ("endpoint", models.TextField(unique=True, verbose_name="Push Endpoint")),
                ("p256dh", models.TextField(verbose_name="p256dh key")),
                ("auth", models.TextField(verbose_name="auth secret")),
                ("user_agent", models.CharField(blank=True, max_length=300)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_used", models.DateTimeField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="push_subscriptions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="push_subscriptions",
                        to="core.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "اشتراك Push",
                "verbose_name_plural": "اشتراكات Push",
                "ordering": ["-created_at"],
            },
        ),
    ]
