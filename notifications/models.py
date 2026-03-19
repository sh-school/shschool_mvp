"""
notifications/models.py
نظام الإشعارات — بريد إلكتروني + SMS
"""
import uuid
from django.db import models
from core.models import School, CustomUser


def _uuid():
    return uuid.uuid4()


class NotificationLog(models.Model):
    """سجل كل إشعار أُرسل"""
    CHANNEL = [
        ("email", "بريد إلكتروني"),
        ("sms",   "SMS"),
    ]
    TYPE = [
        ("absence_alert",  "تنبيه غياب"),
        ("fail_alert",     "تنبيه رسوب"),
        ("grade_report",   "تقرير درجات"),
        ("custom",         "رسالة مخصصة"),
    ]
    STATUS = [
        ("sent",    "أُرسل"),
        ("failed",  "فشل"),
        ("pending", "معلّق"),
    ]

    id           = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school       = models.ForeignKey(School,     on_delete=models.CASCADE, related_name="notification_logs")
    student      = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="notification_logs", verbose_name="الطالب")
    recipient    = models.CharField(max_length=200, verbose_name="المستلم (email/رقم)")
    channel      = models.CharField(max_length=10, choices=CHANNEL, default="email")
    notif_type   = models.CharField(max_length=20, choices=TYPE, default="custom")
    subject      = models.CharField(max_length=300, blank=True, verbose_name="الموضوع")
    body         = models.TextField(verbose_name="نص الرسالة")
    status       = models.CharField(max_length=10, choices=STATUS, default="pending", db_index=True)
    error_msg    = models.TextField(blank=True)
    sent_at      = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_by      = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="sent_notifications")

    class Meta:
        verbose_name        = "إشعار مُرسل"
        verbose_name_plural = "سجل الإشعارات"
        ordering            = ["-sent_at"]
        indexes             = [models.Index(fields=["school", "notif_type", "status"])]

    def __str__(self):
        return f"{self.get_notif_type_display()} → {self.recipient} ({self.get_status_display()})"


class NotificationSettings(models.Model):
    """إعدادات الإشعارات لكل مدرسة"""
    school = models.OneToOneField(School, on_delete=models.CASCADE, related_name="notif_settings")

    # البريد الإلكتروني
    email_enabled           = models.BooleanField(default=True)
    absence_threshold       = models.IntegerField(default=3, verbose_name="حد الغياب (حصص)")
    absence_email_enabled   = models.BooleanField(default=True)
    fail_email_enabled      = models.BooleanField(default=True)
    from_name               = models.CharField(max_length=100, default="إدارة المدرسة")
    reply_to                = models.EmailField(blank=True)

    # SMS (Twilio أو أي مزود)
    sms_enabled             = models.BooleanField(default=False)
    sms_provider            = models.CharField(max_length=20, default="twilio",
                                               choices=[("twilio","Twilio"),("local","محلي")])
    sms_from_number         = models.CharField(max_length=20, blank=True)
    twilio_account_sid      = models.CharField(max_length=100, blank=True)
    twilio_auth_token       = models.CharField(max_length=100, blank=True)

    # نصوص الرسائل (قابلة للتخصيص)
    absence_email_subject   = models.CharField(max_length=200,
        default="تنبيه: غياب متكرر للطالب {student_name}")
    fail_email_subject      = models.CharField(max_length=200,
        default="إشعار: نتيجة الطالب {student_name}")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "إعدادات الإشعارات"
        verbose_name_plural = "إعدادات الإشعارات"

    def __str__(self):
        return f"إعدادات إشعارات — {self.school.name}"
