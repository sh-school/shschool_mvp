"""
Developer Feedback — Admin (v1.0)

تسجيل الخمسة نماذج في Django Admin للمراجعة فقط
(ليس الـ Inbox التشغيلي — هذا سيأتي في جولات لاحقة).
"""

from django.contrib import admin

from .models import (
    AuditLog,
    DeveloperMessage,
    DeveloperMessageNotification,
    LegalOnboardingConsent,
    MessageStatusLog,
)


@admin.register(DeveloperMessage)
class DeveloperMessageAdmin(admin.ModelAdmin):
    list_display = (
        "ticket_number",
        "message_type",
        "priority",
        "status",
        "user",
        "created_at",
    )
    list_filter = ("status", "priority", "message_type")
    search_fields = ("ticket_number", "subject", "body")
    readonly_fields = (
        "ticket_number",
        "user_id_hash",
        "context_json",
        "created_at",
        "updated_at",
        "deletion_scheduled_at",
    )
    ordering = ("-created_at",)
    date_hierarchy = "created_at"


@admin.register(MessageStatusLog)
class MessageStatusLogAdmin(admin.ModelAdmin):
    list_display = (
        "message",
        "old_status",
        "new_status",
        "changed_by",
        "changed_at",
    )
    list_filter = ("new_status", "old_status")
    search_fields = ("message__ticket_number", "note")
    readonly_fields = ("changed_at",)
    ordering = ("-changed_at",)


@admin.register(DeveloperMessageNotification)
class DeveloperMessageNotificationAdmin(admin.ModelAdmin):
    list_display = (
        "message",
        "channel",
        "recipient",
        "status",
        "sent_at",
        "attempt_count",
    )
    list_filter = ("channel", "status")
    search_fields = ("message__ticket_number", "recipient")
    ordering = ("-sent_at",)


@admin.register(LegalOnboardingConsent)
class LegalOnboardingConsentAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "consent_version",
        "accepted_at",
        "quiz_passed",
        "quiz_score",
    )
    list_filter = ("consent_version", "quiz_passed")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("accepted_at",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "actor",
        "action",
        "target_message",
        "created_at",
    )
    list_filter = ("action",)
    search_fields = ("actor__username", "target_message__ticket_number")
    readonly_fields = (
        "actor",
        "action",
        "target_message",
        "ip_address",
        "created_at",
    )
    ordering = ("-created_at",)
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        # سجلات التدقيق تُكتب بواسطة الخدمة فقط — لا يدوياً
        return False

    def has_delete_permission(self, request, obj=None):
        # ممنوع حذف سجلات التدقيق من الواجهة — ثبات الأثر القانوني
        return False
