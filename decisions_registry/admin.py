"""سجلُّ القرارات في الإدارة: قراءةٌ فقط لمن يملك القدرة `decisions.view` (المدير) — لا إضافةَ ولا تعديلَ ولا حذف."""

from django.contrib import admin

from core.capabilities import has_capability

from .models import Decision, ImportBatch


class _ReadOnlyAdmin(admin.ModelAdmin):
    show_full_result_count = False

    def has_module_permission(self, request):
        return has_capability(request.user, "decisions.view")

    def has_view_permission(self, request, obj=None):
        return has_capability(request.user, "decisions.view")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Decision)
class DecisionAdmin(_ReadOnlyAdmin):
    list_display = ("decision_id", "decided_at_text", "kind", "short_text")
    list_filter = ("kind",)
    search_fields = ("decision_id", "text", "effect", "reference")
    ordering = ("decision_id",)

    @admin.display(description="النصّ")
    def short_text(self, obj):
        return obj.text[:120]


@admin.register(ImportBatch)
class ImportBatchAdmin(_ReadOnlyAdmin):
    list_display = ("imported_at", "row_count", "created_count", "names_masked", "file_fingerprint")
    ordering = ("-imported_at",)
