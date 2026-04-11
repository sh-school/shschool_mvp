"""
Developer Feedback — Models (v1.0)

المرجع: PRD-SOS-DEV-FEEDBACK-v1.0 + MTG-2026-014 + MTG-2026-015
القرار E1 المعتمد: لا مرفقات في MVP — نص فقط — Retention 90 يوم.

الخمسة نماذج:
  1. DeveloperMessage            — الرسالة نفسها
  2. MessageStatusLog            — سجل تغيّر الحالة
  3. DeveloperMessageNotification — إشعارات SMTP/InApp
  4. LegalOnboardingConsent      — موافقة قانونية إلزامية قبل أول استخدام
  5. AuditLog                    — سجل وصول Inbox (تصفّح/تحديث/حذف)
"""

from django.conf import settings
from django.core.validators import MaxLengthValidator, MinLengthValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

# ═══════════════════════════════════════════════════════════════
# Choices
# ═══════════════════════════════════════════════════════════════


class MessageType(models.TextChoices):
    BUG = "bug", _("عطل / مشكلة")
    FEATURE = "feature", _("اقتراح ميزة")
    QUESTION = "question", _("سؤال")
    COMPLAINT = "complaint", _("شكوى")
    PRAISE = "praise", _("شكر / ثناء")
    OTHER = "other", _("أخرى")


class MessagePriority(models.TextChoices):
    LOW = "low", _("منخفضة")
    NORMAL = "normal", _("عادية")
    HIGH = "high", _("عالية")


class MessageStatus(models.TextChoices):
    NEW = "new", _("جديدة")
    SEEN = "seen", _("تمّت القراءة")
    IN_PROGRESS = "in_progress", _("قيد المعالجة")
    RESOLVED = "resolved", _("تمّ الحل")
    CLOSED = "closed", _("مغلقة")


class NotificationChannel(models.TextChoices):
    SMTP = "smtp", _("بريد إلكتروني")
    INAPP = "inapp", _("داخل التطبيق")


class NotificationStatus(models.TextChoices):
    PENDING = "pending", _("قيد الانتظار")
    SENT = "sent", _("أُرسلت")
    FAILED = "failed", _("فشل الإرسال")
    RETRY = "retry", _("إعادة محاولة")


class AuditAction(models.TextChoices):
    VIEW_INBOX = "view_inbox", _("عرض صندوق الوارد")
    VIEW_MESSAGE = "view_message", _("عرض رسالة")
    UPDATE_STATUS = "update_status", _("تحديث الحالة")
    DELETE_MESSAGE = "delete_message", _("حذف رسالة")


# ═══════════════════════════════════════════════════════════════
# 1. DeveloperMessage
# ═══════════════════════════════════════════════════════════════


class DeveloperMessage(models.Model):
    """
    رسالة يرسلها المستخدم (غير الطالب) إلى المطوّر.

    - المرفقات ملغاة في MVP (قرار E1)
    - نص فقط: subject 5-200 حرف + body 10-4000 حرف
    - context_json يحوي url_path/view_name/viewport/role فقط
      (بدون tokens/IP/UA حفاظاً على الخصوصية)
    - deletion_scheduled_at = created_at + 90 يوم (يُحسب تلقائياً في save)
    """

    RETENTION_DAYS = 90

    id = models.BigAutoField(primary_key=True)

    ticket_number = models.CharField(
        _("رقم التذكرة"),
        max_length=20,
        unique=True,
        help_text=_("صيغة: SOS-YYYYMMDD-XXXX"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dev_feedback_messages",
        verbose_name=_("المستخدم"),
    )

    user_id_hash = models.CharField(
        _("بصمة المستخدم (SHA-256)"),
        max_length=64,
        help_text=_("تُستخدم في إيميل المطوّر بدلاً من معرّف المستخدم الفعلي"),
    )

    message_type = models.CharField(
        _("نوع الرسالة"),
        max_length=20,
        choices=MessageType.choices,
        default=MessageType.OTHER,
    )

    priority = models.CharField(
        _("الأولوية"),
        max_length=10,
        choices=MessagePriority.choices,
        default=MessagePriority.NORMAL,
    )

    subject = models.CharField(
        _("الموضوع"),
        max_length=200,
        validators=[
            MinLengthValidator(5),
            MaxLengthValidator(200),
        ],
    )

    body = models.TextField(
        _("نصّ الرسالة"),
        validators=[
            MinLengthValidator(10),
            MaxLengthValidator(4000),
        ],
    )

    context_json = models.JSONField(
        _("السياق التقني"),
        default=dict,
        blank=True,
        help_text=_("url_path, view_name, viewport, role — لا tokens ولا IP ولا UA"),
    )

    status = models.CharField(
        _("الحالة"),
        max_length=15,
        choices=MessageStatus.choices,
        default=MessageStatus.NEW,
    )

    consent_given_at = models.DateTimeField(
        _("وقت إعطاء الموافقة"),
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(_("أُنشئت في"), auto_now_add=True)
    updated_at = models.DateTimeField(_("آخر تحديث"), auto_now=True)

    deletion_scheduled_at = models.DateTimeField(
        _("موعد الحذف المجدول"),
        null=True,
        blank=True,
        help_text=_("يُحسب تلقائياً = created_at + 90 يوم (بعد أول حفظ)"),
    )

    class Meta:
        verbose_name = _("رسالة إلى المطوّر")
        verbose_name_plural = _("رسائل المطوّر")
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["status", "created_at"],
                name="devfb_msg_status_created_idx",
            ),
            models.Index(
                fields=["user", "created_at"],
                name="devfb_msg_user_created_idx",
            ),
            models.Index(
                fields=["priority", "status"],
                name="devfb_msg_priority_status_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.ticket_number} — {self.subject}"

    def save(self, *args, **kwargs):
        """
        ترتيب الحفظ:
          1) توليد ticket_number فريد (إن لم يكن مضبوطاً).
          2) حساب user_id_hash من خدمة hashing (إن كان user موجوداً وفارغاً).
          3) super().save() — الآن created_at و pk حقيقيان.
          4) حساب deletion_scheduled_at = created_at + 90 يوم بعد الحفظ.
        """
        from datetime import timedelta

        is_new = self._state.adding

        # 1) ticket_number — توليد فريد قبل الحفظ
        if not self.ticket_number:
            from developer_feedback.services.ticketing import (
                generate_unique_ticket_number,
            )

            self.ticket_number = generate_unique_ticket_number(type(self))

        # 2) user_id_hash — احسب hash آمن قبل الحفظ إن كان غير معبَّأ
        if self.user_id and not self.user_id_hash:
            from developer_feedback.services.hashing import hash_user_id

            self.user_id_hash = hash_user_id(self.user_id)

        super().save(*args, **kwargs)

        # 3) بعد super: created_at مضمون + pk موجود
        if is_new and not self.deletion_scheduled_at:
            self.deletion_scheduled_at = self.created_at + timedelta(days=self.RETENTION_DAYS)
            super().save(update_fields=["deletion_scheduled_at"])


# ═══════════════════════════════════════════════════════════════
# 2. MessageStatusLog
# ═══════════════════════════════════════════════════════════════


class MessageStatusLog(models.Model):
    """سجل تغيير حالة رسالة — لتتبّع Who/When/What/Why."""

    id = models.BigAutoField(primary_key=True)

    message = models.ForeignKey(
        DeveloperMessage,
        on_delete=models.CASCADE,
        related_name="status_logs",
        verbose_name=_("الرسالة"),
    )

    old_status = models.CharField(
        _("الحالة السابقة"),
        max_length=15,
        choices=MessageStatus.choices,
    )

    new_status = models.CharField(
        _("الحالة الجديدة"),
        max_length=15,
        choices=MessageStatus.choices,
    )

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dev_feedback_status_changes",
        verbose_name=_("غيّرها"),
    )

    changed_at = models.DateTimeField(_("وقت التغيير"), auto_now_add=True)

    note = models.TextField(_("ملاحظة"), blank=True)

    class Meta:
        verbose_name = _("سجل تغيير حالة رسالة")
        verbose_name_plural = _("سجلات تغيير الحالات")
        ordering = ["-changed_at"]

    def __str__(self) -> str:
        return f"{self.message_id}: {self.old_status} → {self.new_status}"


# ═══════════════════════════════════════════════════════════════
# 3. DeveloperMessageNotification
# ═══════════════════════════════════════════════════════════════


class DeveloperMessageNotification(models.Model):
    """إشعارات SMTP / داخل التطبيق للمطوّر عند وصول رسالة جديدة."""

    id = models.BigAutoField(primary_key=True)

    message = models.ForeignKey(
        DeveloperMessage,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name=_("الرسالة"),
    )

    channel = models.CharField(
        _("القناة"),
        max_length=15,
        choices=NotificationChannel.choices,
    )

    recipient = models.CharField(_("المستلِم"), max_length=200)

    sent_at = models.DateTimeField(_("وقت الإرسال"), null=True, blank=True)

    status = models.CharField(
        _("حالة الإشعار"),
        max_length=15,
        choices=NotificationStatus.choices,
        default=NotificationStatus.PENDING,
    )

    error_detail = models.TextField(_("تفاصيل الخطأ"), blank=True)

    attempt_count = models.PositiveSmallIntegerField(
        _("عدد المحاولات"),
        default=0,
    )

    created_at = models.DateTimeField(
        _("تاريخ الإنشاء"),
        auto_now_add=True,
    )

    class Meta:
        verbose_name = _("إشعار رسالة مطوّر")
        verbose_name_plural = _("إشعارات رسائل المطوّر")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.channel} → {self.recipient} ({self.status})"


# ═══════════════════════════════════════════════════════════════
# 4. LegalOnboardingConsent
# ═══════════════════════════════════════════════════════════════


class LegalOnboardingConsent(models.Model):
    """
    موافقة قانونية إلزامية قبل أول استخدام للميزة.

    المتطلبات:
      - مشاهدة شاشة Onboarding (3 دقائق)
      - اجتياز اختبار صغير (quiz_passed + quiz_score)
      - مرجع تفويض إداري كتابي من المدير (admin_authorization_doc)
    """

    id = models.BigAutoField(primary_key=True)

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dev_feedback_consent",
        verbose_name=_("المستخدم"),
    )

    consent_version = models.CharField(
        _("إصدار الموافقة"),
        max_length=10,
        default="1.0",
    )

    accepted_at = models.DateTimeField(_("وقت القبول"), auto_now_add=True)

    quiz_passed = models.BooleanField(_("اجتاز الاختبار؟"), default=False)

    quiz_score = models.PositiveSmallIntegerField(
        _("درجة الاختبار"),
        default=0,
    )

    admin_authorization_doc = models.CharField(
        _("مرجع التفويض الإداري الكتابي"),
        max_length=255,
        blank=True,
    )

    revoked_at = models.DateTimeField(_("وقت الإلغاء"), null=True, blank=True)

    class Meta:
        verbose_name = _("موافقة الإعداد القانوني")
        verbose_name_plural = _("موافقات الإعداد القانوني")

    def __str__(self) -> str:
        return f"{self.user} — v{self.consent_version}"


# ═══════════════════════════════════════════════════════════════
# 5. AuditLog
# ═══════════════════════════════════════════════════════════════


class AuditLog(models.Model):
    """سجل وصول للـ Inbox — يسجّل كل عرض/تحديث/حذف للرسائل."""

    id = models.BigAutoField(primary_key=True)

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dev_feedback_audit_entries",
        verbose_name=_("الفاعل"),
    )

    action = models.CharField(
        _("الإجراء"),
        max_length=30,
        choices=AuditAction.choices,
    )

    target_message = models.ForeignKey(
        DeveloperMessage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_entries",
        verbose_name=_("الرسالة المستهدفة"),
    )

    ip_address = models.GenericIPAddressField(
        _("عنوان IP"),
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(_("وقت الإجراء"), auto_now_add=True)

    class Meta:
        verbose_name = _("سجل تدقيق الوصول")
        verbose_name_plural = _("سجلات تدقيق الوصول")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.actor} — {self.action} @ {self.created_at:%Y-%m-%d %H:%M}"
