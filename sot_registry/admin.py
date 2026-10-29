"""لوحة Django لسجلِّ مصدر الحقيقة: لا حذفَ نهائيّ من أيّ جدول، والحذفُ الناعمُ بإجراءٍ للمالك وحده."""

from django.contrib import admin, messages

from sot_registry import services
from sot_registry.models import (
    CodeLink,
    Conflict,
    Provision,
    Revision,
    Source,
    Supersession,
    Threshold,
    Topic,
)


class _NoDeleteAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None):
        return False


class _AppendOnlyAdmin(_NoDeleteAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Source)
class SourceAdmin(_NoDeleteAdmin):
    list_display = (
        "code",
        "kind",
        "title",
        "issuer",
        "school_year",
        "expected_count",
        "is_deleted",
    )
    list_filter = ("kind", "school_year", "is_deleted")
    search_fields = ("code", "title", "doc_number", "issuer")


@admin.register(Topic)
class TopicAdmin(_NoDeleteAdmin):
    list_display = ("code", "name", "parent", "is_deleted")
    list_filter = ("is_deleted",)
    search_fields = ("code", "name")


@admin.register(Provision)
class ProvisionAdmin(_NoDeleteAdmin):
    list_display = (
        "pid",
        "source",
        "article",
        "printed_page",
        "status",
        "reviewed_by",
        "is_deleted",
    )
    list_filter = ("source", "status", "topic", "is_deleted")
    search_fields = ("pid", "article", "verbatim", "explanation")
    readonly_fields = ("loaded_by", "reviewed_by", "reviewed_at", "deleted_at", "delete_reason")
    actions = ("soft_delete_selected", "mark_in_review")

    @admin.action(description="حذفٌ ناعمٌ للأحكام المحدَّدة (المالك وحده)")
    def soft_delete_selected(self, request, queryset):
        for provision in queryset:
            try:
                services.soft_delete(request.user, provision, "حذفٌ ناعم من لوحة الإدارة")
            except Exception as exc:  # noqa: BLE001 — يُعرض السببُ للمالك بدل أن يسقط الإجراءُ كلُّه
                self.message_user(request, f"{provision.pid}: {exc}", level=messages.ERROR)

    @admin.action(description="اعتبارُ الأحكام المحدَّدة مراجَعةً بشريًّا (المالك وحده)")
    def mark_in_review(self, request, queryset):
        for provision in queryset:
            try:
                services.mark_reviewed(request.user, provision)
            except Exception as exc:  # noqa: BLE001
                self.message_user(request, f"{provision.pid}: {exc}", level=messages.ERROR)


@admin.register(Threshold)
class ThresholdAdmin(_NoDeleteAdmin):
    list_display = ("provision", "key", "comparator", "value", "unit", "is_deleted")
    list_filter = ("unit", "is_deleted")
    search_fields = ("provision__pid", "key")


@admin.register(Supersession)
class SupersessionAdmin(_NoDeleteAdmin):
    list_display = ("old", "new", "effective_date", "is_deleted")
    list_filter = ("is_deleted",)
    search_fields = ("old__pid", "new__pid", "note")


@admin.register(CodeLink)
class CodeLinkAdmin(_NoDeleteAdmin):
    list_display = ("provision", "code_path", "symbol")
    search_fields = ("provision__pid", "code_path", "symbol")


@admin.register(Revision)
class RevisionAdmin(_AppendOnlyAdmin):
    list_display = ("provision", "action", "actor", "at")
    list_filter = ("action",)
    search_fields = ("provision__pid", "actor")


@admin.register(Conflict)
class ConflictAdmin(_NoDeleteAdmin):
    list_display = ("provision_a", "provision_b", "status")
    list_filter = ("status",)
    search_fields = ("provision_a__pid", "provision_b__pid", "description")
