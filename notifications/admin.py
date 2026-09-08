"""
notifications/admin.py
تسجيل نماذج الإشعارات في لوحة الإدارة — قراءةٌ وتشخيصٌ لا تحرير.

الجداول هنا **سجلّات وقائع**: ما جرى فعلاً من إطلاقٍ وطبرٍ وتسليمٍ ونداءِ
مزوّد. تحريرها من اللوحة يزوّر تاريخاً، لذلك أكثرُها للعرض فقط ولا يُنشأ منها
شيءٌ يدوياً. المستثنى ما هو **إعدادٌ** بطبعه: إعدادات المدرسة وتفضيلات
المستخدم — وهذان يُحرَّران.

والحقولُ المشفَّرة (`auth` في اشتراك Push، ومفاتيح Twilio) لا تُعرض ولا
تُدخَل من هنا: عرضُها يُخرج سرّاً من مخزنه إلى صفحةٍ وسجلّ وصول.
"""

from django.contrib import admin, messages
from django.contrib.admin.models import DELETION, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from .models import (
    DeadLetterMessage,
    InAppNotification,
    NotificationDelivery,
    NotificationDispatch,
    NotificationEnqueueIntent,
    NotificationLog,
    NotificationSettings,
    PushSubscription,
    UserNotificationPreference,
)


class ReadOnlyAdmin(admin.ModelAdmin):
    """سجلُّ وقائع: يُعرض ويُبحث فيه، ولا يُنشأ ولا يُحرَّر."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class PurgeAllMixin:
    """زرُّ «حذف الكلّ» في شاشة القائمة — بحاجزين قبل التنفيذ.

    حذفُ صفٍّ صفّاً في جدولٍ يبلغ مئاتِ الآلاف ليس عملاً إدارياً، ومع ذلك
    فالتفريغُ الكامل فعلٌ لا رجعةَ فيه. لذلك حاجزان: تنبيهُ المتصفّح على الزرّ،
    ثمّ صفحةُ تأكيدٍ تُلزم بكتابة كلمة «حذف» وتُنفَّذ بـPOST وحده — فلا يُفرَّغ
    جدولٌ برابطٍ يُفتح بالخطأ أو يُزار مسبقاً من مُسرِّع المتصفّح.

    والصلاحية للمستخدم الخارق وحده: هذه سجلّاتُ تدقيقٍ يستند إليها غيرُها.
    """

    purge_confirm_template = "admin/notifications/purge_confirm.html"
    change_list_template = "admin/notifications/change_list_purge.html"

    #: نصُّ التحذير في تنبيه المتصفّح — يُعاد تعريفه في كلّ شاشة.
    purge_warning = "سيُحذف كلُّ ما في هذا الجدول نهائياً. أتريد المتابعة؟"

    def _purge_url_name(self):
        meta = self.model._meta
        return f"admin:{meta.app_label}_{meta.model_name}_purge_all"

    def get_urls(self):
        meta = self.model._meta
        custom = [
            path(
                "purge-all/",
                self.admin_site.admin_view(self.purge_all_view),
                name=f"{meta.app_label}_{meta.model_name}_purge_all",
            ),
        ]
        return custom + super().get_urls()

    def has_purge_permission(self, request):
        return request.user.is_superuser and self.has_delete_permission(request)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        if self.has_purge_permission(request):
            extra_context["purge_all_url"] = reverse(self._purge_url_name())
            extra_context["purge_warning"] = self.purge_warning
        return super().changelist_view(request, extra_context=extra_context)

    def purge_all_view(self, request):
        if not self.has_purge_permission(request):
            raise PermissionDenied

        meta = self.model._meta
        queryset = self.model._default_manager.all()
        total = queryset.count()
        changelist_url = reverse(f"admin:{meta.app_label}_{meta.model_name}_changelist")

        if request.method == "POST":
            typed = (request.POST.get("confirm_word") or "").strip()
            if typed not in ("حذف", "DELETE"):
                messages.error(request, "لم تُكتب كلمة التأكيد — لم يُحذف شيء.")
                return redirect(request.path)

            deleted_total, _per_model = queryset.delete()
            # صفٌّ في django_admin_log بلا `object_id`: الواقعةُ تفريغُ جدولٍ لا
            # حذفُ كائنٍ بعينه. ويُبنى الصفُّ مباشرةً لأن `log_action` أُزيل في
            # Django 6.0 و`log_actions` تشتقّ سجلّاتها من صفوفٍ لم تعد موجودة.
            LogEntry.objects.create(
                user=request.user,
                content_type=ContentType.objects.get_for_model(self.model),
                object_repr=f"تفريغ {meta.verbose_name_plural} — {deleted_total} صفّاً"[:200],
                action_flag=DELETION,
                change_message=f"حذف الكلّ من لوحة الإدارة ({deleted_total} صفّاً).",
            )
            messages.success(request, f"تمّ حذف {deleted_total} صفّاً من {meta.verbose_name_plural}.")
            return redirect(changelist_url)

        context = {
            **self.admin_site.each_context(request),
            "title": f"تأكيد حذف كلّ {meta.verbose_name_plural}",
            "opts": meta,
            "total": total,
            "changelist_url": changelist_url,
        }
        return TemplateResponse(request, self.purge_confirm_template, context)


@admin.register(InAppNotification)
class InAppNotificationAdmin(PurgeAllMixin, ReadOnlyAdmin):
    """إشعاراتُ الجرس — الكيان المخزَّن نفسه لا تسليماً خارجياً."""

    list_display = ("title", "user", "event_type", "priority", "is_read", "created_at", "school")
    list_filter = ("event_type", "priority", "is_read", "school", "created_at")
    search_fields = ("title", "body", "user__full_name", "user__national_id")
    autocomplete_fields = ("user", "school")
    date_hierarchy = "created_at"
    list_select_related = ("user", "school")
    ordering = ("-created_at",)
    purge_warning = "سيُحذف جرسُ كلّ مستخدم نهائياً — المقروءُ وغيرُ المقروء. أتريد المتابعة؟"


@admin.register(NotificationDispatch)
class NotificationDispatchAdmin(ReadOnlyAdmin):
    """واقعةُ الإطلاق — «لماذا نُرسل؟»."""

    list_display = ("event_type", "school", "sent_by", "related_object_id", "created_at")
    list_filter = ("event_type", "school", "created_at")
    search_fields = ("event_type", "related_object_id", "sent_by__full_name")
    autocomplete_fields = ("school", "sent_by")
    date_hierarchy = "created_at"
    list_select_related = ("school", "sent_by")
    ordering = ("-created_at",)


@admin.register(NotificationDelivery)
class NotificationDeliveryAdmin(ReadOnlyAdmin):
    """تسليمٌ لمستلمٍ واحدٍ على قناةٍ واحدة — وحدةُ الفشل."""

    list_display = (
        "recipient",
        "channel",
        "status",
        "attempt_count",
        "status_changed_at",
        "school",
    )
    list_filter = ("channel", "status", "school", "created_at")
    search_fields = ("recipient__full_name", "recipient__national_id", "dispatch__event_type")
    autocomplete_fields = ("recipient", "school")
    raw_id_fields = ("dispatch",)
    date_hierarchy = "created_at"
    list_select_related = ("recipient", "school", "dispatch")
    ordering = ("-created_at",)


@admin.register(NotificationEnqueueIntent)
class NotificationEnqueueIntentAdmin(ReadOnlyAdmin):
    """صندوقُ الصادر المؤقّت — يحمل النصَّ حتى يُمسح بعد نهائيّة التسليمات.

    `title` و`body` خارج العرض والبحث عمداً: هما محتوى رسالةٍ عن طالبٍ بعينه،
    والغرضُ من الشاشة تشخيصُ الطبر لا قراءةُ المراسلات.
    """

    list_display = (
        "id",
        "recipient",
        "school",
        "last_enqueue_attempt_at",
        "content_cleared_at",
        "created_at",
    )
    list_filter = ("school", "created_at", "content_cleared_at")
    search_fields = ("recipient__full_name", "dispatch__event_type")
    autocomplete_fields = ("recipient", "school")
    raw_id_fields = ("dispatch",)
    date_hierarchy = "created_at"
    list_select_related = ("recipient", "school")
    ordering = ("-created_at",)


@admin.register(NotificationLog)
class NotificationLogAdmin(PurgeAllMixin, ReadOnlyAdmin):
    """محاولةُ نداءِ مزوّدٍ واحدة — صفٌّ لكلّ محاولةٍ لا لكلّ رسالة."""

    list_display = ("notif_type", "channel", "recipient", "status", "sent_at", "school")
    list_filter = ("channel", "notif_type", "status", "school", "sent_at")
    search_fields = ("recipient", "subject", "student__full_name")
    autocomplete_fields = ("school", "student", "sent_by")
    raw_id_fields = ("delivery",)
    date_hierarchy = "sent_at"
    list_select_related = ("school", "student")
    ordering = ("-sent_at",)
    purge_warning = "سيُحذف سجلُّ محاولات الإرسال كلُّه نهائياً. أتريد المتابعة؟"


@admin.register(DeadLetterMessage)
class DeadLetterMessageAdmin(ReadOnlyAdmin):
    """طابورُ الرسائل الميّتة — شهادةُ فشلٍ استنفد محاولاته.

    الحمولةُ تشخيصيّةٌ لا نسخةٌ من الرسالة، وإعادةُ الإرسال محجوبةٌ من هنا:
    لا يوجد في الصفّ ما يستعيد المستلمَ في كلّ الحالات.
    """

    list_display = ("kind", "school", "resolved", "created_at")
    list_filter = ("kind", "resolved", "school", "created_at")
    search_fields = ("error",)
    autocomplete_fields = ("school",)
    raw_id_fields = ("delivery",)
    date_hierarchy = "created_at"
    list_select_related = ("school",)
    ordering = ("-created_at",)


@admin.register(PushSubscription)
class PushSubscriptionAdmin(ReadOnlyAdmin):
    """اشتراكُ متصفّحٍ بـ Web Push — `auth` مشفَّرٌ ولا يُعرض."""

    list_display = ("user", "school", "is_active", "created_at", "last_used")
    list_filter = ("is_active", "school", "created_at")
    search_fields = ("user__full_name", "user__national_id")
    autocomplete_fields = ("user", "school")
    date_hierarchy = "created_at"
    list_select_related = ("user", "school")
    ordering = ("-created_at",)

    def get_exclude(self, request, obj=None):
        return ("_auth", "p256dh", "endpoint")


@admin.register(NotificationSettings)
class NotificationSettingsAdmin(admin.ModelAdmin):
    """إعداداتُ المدرسة — تُحرَّر، وأسرارُ Twilio مستثناةٌ من النموذج."""

    list_display = ("school", "email_enabled", "sms_enabled", "sms_provider", "updated_at")
    list_filter = ("email_enabled", "sms_enabled", "sms_provider")
    search_fields = ("school__name", "school__code")
    autocomplete_fields = ("school",)
    list_select_related = ("school",)

    def get_exclude(self, request, obj=None):
        return ("_twilio_account_sid", "_twilio_auth_token")


@admin.register(UserNotificationPreference)
class UserNotificationPreferenceAdmin(admin.ModelAdmin):
    """تفضيلاتُ المستخدم — إعدادٌ يُحرَّر لا واقعةٌ تُحفظ."""

    list_display = (
        "user",
        "in_app_enabled",
        "push_enabled",
        "email_enabled",
        "sms_enabled",
        "whatsapp_enabled",
        "updated_at",
    )
    list_filter = ("in_app_enabled", "push_enabled", "email_enabled", "sms_enabled")
    search_fields = ("user__full_name", "user__national_id")
    autocomplete_fields = ("user",)
    list_select_related = ("user",)
