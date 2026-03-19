from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("core", "0001_phase2_schedule_substitute"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="NotificationSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("email_enabled",           models.BooleanField(default=True)),
                ("absence_threshold",       models.IntegerField(default=3)),
                ("absence_email_enabled",   models.BooleanField(default=True)),
                ("fail_email_enabled",      models.BooleanField(default=True)),
                ("from_name",               models.CharField(default="إدارة المدرسة", max_length=100)),
                ("reply_to",                models.EmailField(blank=True)),
                ("sms_enabled",             models.BooleanField(default=False)),
                ("sms_provider",            models.CharField(default="twilio", max_length=20)),
                ("sms_from_number",         models.CharField(blank=True, max_length=20)),
                ("twilio_account_sid",      models.CharField(blank=True, max_length=100)),
                ("twilio_auth_token",       models.CharField(blank=True, max_length=100)),
                ("absence_email_subject",   models.CharField(default="تنبيه: غياب متكرر للطالب {student_name}", max_length=200)),
                ("fail_email_subject",      models.CharField(default="إشعار: نتيجة الطالب {student_name}", max_length=200)),
                ("updated_at",              models.DateTimeField(auto_now=True)),
                ("school",                  models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="notif_settings", to="core.school")),
            ],
            options={"verbose_name": "إعدادات الإشعارات", "verbose_name_plural": "إعدادات الإشعارات"},
        ),
        migrations.CreateModel(
            name="NotificationLog",
            fields=[
                ("id",         models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("recipient",  models.CharField(max_length=200)),
                ("channel",    models.CharField(choices=[("email","بريد إلكتروني"),("sms","SMS")], default="email", max_length=10)),
                ("notif_type", models.CharField(choices=[("absence_alert","تنبيه غياب"),("fail_alert","تنبيه رسوب"),("grade_report","تقرير درجات"),("custom","رسالة مخصصة")], default="custom", max_length=20)),
                ("subject",    models.CharField(blank=True, max_length=300)),
                ("body",       models.TextField()),
                ("status",     models.CharField(choices=[("sent","أُرسل"),("failed","فشل"),("pending","معلّق")], db_index=True, default="pending", max_length=10)),
                ("error_msg",  models.TextField(blank=True)),
                ("sent_at",    models.DateTimeField(auto_now_add=True, db_index=True)),
                ("school",     models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notification_logs", to="core.school")),
                ("sent_by",    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sent_notifications", to=settings.AUTH_USER_MODEL)),
                ("student",    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="notification_logs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "إشعار مُرسل", "verbose_name_plural": "سجل الإشعارات", "ordering": ["-sent_at"]},
        ),
        migrations.AddIndex(
            model_name="notificationlog",
            index=models.Index(fields=["school", "notif_type", "status"], name="notif_school_type_idx"),
        ),
    ]
